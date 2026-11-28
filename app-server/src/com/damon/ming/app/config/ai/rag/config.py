# app-server/src/com/damon/ming/app/config/ai/rag/config.py
"""加载 RAG YAML，并解析应用侧请求预算与提示词配置。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.com.damon.ming.utils.yaml_loader import load_yaml


@dataclass(frozen=True, kw_only=True)
class RagPromptConfig:
    """rag.prompt 段：参考资料标签、问题标签和系统提示词。"""

    ref_label: str
    query_label: str
    system_prompt: str

    def __post_init__(self) -> None:
        for name in ("ref_label", "query_label", "system_prompt"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"rag.prompt.{name} 必须是非空字符串")

    @classmethod
    def from_mapping(cls, raw: Any) -> RagPromptConfig:
        if not isinstance(raw, dict):
            raise TypeError("rag.prompt 必须是配置映射")
        try:
            return cls(
                ref_label=raw["ref_label"],
                query_label=raw["query_label"],
                system_prompt=raw["system_prompt"],
            )
        except KeyError as exc:
            raise ValueError(f"rag.prompt 缺少必填字段: {exc}") from exc


@dataclass(frozen=True, kw_only=True)
class RagConfig:
    """rag 段。"""

    execution_timeout_seconds: float  # 检索、上下文构造和主推理预算（秒），不含护栏
    context_max_tokens: int  # 返回给主推理模型的参考上下文 token 上限
    max_concurrency: int
    retry_ms: int
    prompt: RagPromptConfig

    @classmethod
    def from_mapping(cls, rag: Any) -> RagConfig:
        if not isinstance(rag, dict):
            raise TypeError("运行时配置缺少 rag 段")

        try:
            return cls(
                context_max_tokens=cls._integer(
                    rag["context_max_tokens"], "rag.context_max_tokens"
                ),
                execution_timeout_seconds=cls._positive_number(
                    rag["execution_timeout_seconds"],
                    "rag.execution_timeout_seconds",
                ),
                max_concurrency=cls._integer(
                    rag["max_concurrency"],
                    "rag.max_concurrency",
                ),
                retry_ms=cls._integer(
                    rag["retry_ms"],
                    "rag.retry_ms",
                    minimum=0,
                ),
                prompt=RagPromptConfig.from_mapping(rag["prompt"]),
            )
        except KeyError as e:
            raise ValueError(f"rag 缺少必填字段: {e}") from e

    @staticmethod
    def _positive_number(value: object, path: str) -> float:
        """超时必须是有限正数，不做字符串或布尔值转换。"""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{path} 必须是有限正数")
        timeout = float(value)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(f"{path} 必须是有限正数")
        return timeout

    @staticmethod
    def _integer(value: object, path: str, *, minimum: int = 1) -> int:
        if type(value) is not int or value < minimum:
            raise ValueError(f"{path} 必须是大于等于 {minimum} 的整数")
        return value


class RagConfigLoader:
    """加载一层模块引用，展开显式提供的变量，缓存配置字典。"""

    def __init__(
        self,
        *,
        variables: dict[str, str] | None = None,
        deferred_variables: set[str] | None = None,
    ) -> None:
        self._config_dir = Path(__file__).resolve().parent
        self._variables = dict(variables or {})
        self._deferred_variables = frozenset(deferred_variables or ())
        self._config: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        """展开入口和 include 的变量，解析资源路径；字段语义由各使用方校验。"""
        if self._config is None:
            raw = load_yaml(self._config_dir / "rag-runtime.yaml")
            raw = self._expand_variables(raw, "root")
            raw["modules"] = self._load_modules(raw.get("modules"))
            self._config = raw
        return self._config

    def _expand_variables(self, value: Any, location: str) -> Any:
        if isinstance(value, dict):
            return {
                key: self._expand_variables(item, f"{location}.{key}")
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._expand_variables(item, f"{location}[{index}]")
                for index, item in enumerate(value)
            ]
        if not isinstance(value, str):
            return value

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name in self._deferred_variables:
                return match.group(0)
            if name not in self._variables:
                raise ValueError(f"RAG 配置变量 '{name}' 未提供 | path={location}")
            replacement = self._variables[name]
            if not isinstance(replacement, str) or not replacement.strip():
                raise ValueError(
                    f"RAG 配置变量 '{name}' 必须是非空字符串 | path={location}"
                )
            return replacement

        return re.sub(r"\$\{([^{}]+)\}", replace, value)

    def _load_modules(self, raw: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(raw, dict) or not raw:
            raise TypeError("RAG 配置缺少有效的 modules 段")
        modules: dict[str, dict[str, Any]] = {}
        for name, reference in raw.items():
            if not isinstance(reference, dict) or set(reference) != {"include"}:
                raise ValueError(f"modules.{name} 必须只声明 include 文件路径")
            location = reference["include"]
            if not isinstance(location, str) or not location.strip():
                raise ValueError(f"modules.{name}.include 必须是非空字符串")
            path = Path(location)
            if path.is_absolute() or path.suffix.lower() not in {".yaml", ".yml"}:
                raise ValueError(f"modules.{name}.include 必须是相对 YAML 文件路径")
            module_path = self._config_dir / path
            module = load_yaml(module_path)
            if "include" in module:
                raise ValueError(f"modules.{name} 不支持嵌套 include")
            module = self._expand_variables(module, f"root.modules.{name}")
            if name == "tokenizer":
                self._resolve_tokenizer_dict_paths(module, module_path.parent)
            modules[name] = module
        return modules

    @staticmethod
    def _resolve_tokenizer_dict_paths(module: dict[str, Any], config_dir: Path) -> None:
        """业务词典的相对路径以 tokenizer YAML 所在目录为基准。"""
        roles = module.get("roles")
        if not isinstance(roles, dict):
            return
        for role in roles.values():
            if not isinstance(role, dict) or role.get("tokenizer_engine") != "jieba":
                continue
            params = role.get("params")
            if not isinstance(params, dict):
                continue
            location = params.get("dicts_dir")
            if not isinstance(location, str) or not location.strip():
                continue
            path = Path(location.strip())
            if not path.is_absolute():
                path = config_dir / path
            params["dicts_dir"] = str(path.resolve())

    def get_rag_config(self) -> dict[str, Any]:
        return self._get_section("rag")

    def get_modules_config(self) -> dict[str, Any]:
        return self._get_section("modules")

    def get_embedding_config(self) -> dict[str, Any]:
        return self._get_section("modules", "embedding")

    def _get_section(self, *path: str) -> dict[str, Any]:
        section = self.load()
        for index, name in enumerate(path):
            value = section.get(name)
            if not isinstance(value, dict):
                location = ".".join(path[: index + 1])
                raise TypeError(f"RAG 配置缺少有效的 {location} 段")
            section = value
        return section
