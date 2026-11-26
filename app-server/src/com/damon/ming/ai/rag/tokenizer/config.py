"""映射 tokenizer YAML，并转换为内部使用的参数对象。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.com.damon.ming.ai.rag.tokenizer.params import (
    JiebaTokenizerParams,
    TiktokenTokenizerParams,
    TokenizerParams,
    TokenizerRoleParams,
)


@dataclass(frozen=True, kw_only=True)
class TokenizerConfig:
    roles: dict[str, TokenizerRoleParams]

    def __post_init__(self) -> None:
        if not isinstance(self.roles, dict) or not self.roles:
            raise ValueError("RAG tokenizer 配置缺少 roles")
        if not all(
            isinstance(role, TokenizerRoleParams) for role in self.roles.values()
        ):
            raise TypeError("RAG tokenizer roles 必须使用 TokenizerRoleParams")

    @classmethod
    def from_mapping(cls, raw: Any) -> TokenizerConfig:
        if not isinstance(raw, dict):
            raise TypeError("RAG tokenizer 配置必须是键值对象")
        raw_roles = raw.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("RAG tokenizer 配置缺少 roles")
        roles: dict[str, TokenizerRoleParams] = {}
        for name, entry in raw_roles.items():
            if not isinstance(entry, dict):
                raise TypeError(f"分词器配置 '{name}' 必须是键值对象")
            try:
                engine = entry.get("tokenizer_engine")
                params = cls._parse_params(engine, entry.get("params", {}))
                roles[name] = TokenizerRoleParams(
                    tokenizer_engine=engine,
                    params=params,
                )
            except (TypeError, ValueError, FileNotFoundError) as exc:
                raise type(exc)(f"分词器配置 '{name}' 无效: {exc}") from exc
        return cls(roles=roles)

    @staticmethod
    def _parse_params(engine: Any, raw: Any) -> TokenizerParams:
        if not isinstance(engine, str) or not engine.strip():
            raise ValueError("配置缺少有效的 tokenizer_engine 字段")
        if not isinstance(raw, dict):
            raise TypeError("分词器 params 必须是键值对象")
        if engine == "tiktoken":
            return TiktokenTokenizerParams(encoding_name=raw.get("encoding_name"))
        if engine == "jieba":
            return JiebaTokenizerParams(
                user_dict_paths=TokenizerConfig._discover_jieba_dict_paths(
                    raw.get("dicts_dir")
                )
            )
        raise ValueError(f"分词器引擎 '{engine}' 尚未配置对应的参数解析器")

    @staticmethod
    def _discover_jieba_dict_paths(location: Any) -> tuple[str, ...]:
        if location is None:
            return ()
        if not isinstance(location, str):
            raise TypeError("params.dicts_dir 必须是字符串")
        location = location.strip()
        if not location:
            return ()
        dicts_dir = Path(location)
        if not dicts_dir.is_absolute():
            raise ValueError("params.dicts_dir 必须由应用配置加载器解析为绝对路径")
        dicts_dir = dicts_dir.resolve()
        if not dicts_dir.is_dir():
            raise FileNotFoundError(f"词典目录不存在: {dicts_dir}")
        return tuple(
            str(path.resolve())
            for path in sorted(dicts_dir.glob("*.txt"))
            if path.is_file()
        )
