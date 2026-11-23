"""加载 AI 推理配置并在启动时装配共享的引擎客户端。"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.com.damon.ming.ai.inference import resolve_engine
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
)
from src.com.damon.ming.app.config.env import (
    get_inference_gateway_url,
    get_inference_server,
)
from src.com.damon.ming.utils.yaml_loader import load_yaml


@dataclass(frozen=True)
class ModelEntry:
    model_name: str
    options: dict[str, Any]
    api_key: str
    engine_type: str
    engine: BaseInferenceService
    timeout_seconds: float | None
    context_window_tokens: int | None


@dataclass(frozen=True)
class InferenceConfig:
    max_concurrency: int
    timeout_seconds: float
    roles: dict[str, ModelEntry]


class InferenceConfigLoader:
    """按 API key 复用客户端，重复加载时返回同一配置。"""

    def __init__(self) -> None:
        self._config: InferenceConfig | None = None
        self._config_dir = str(Path(__file__).resolve().parent)

    def load(self) -> InferenceConfig:
        if self._config is not None:
            return self._config
        raw = load_yaml(self._config_dir)
        if not isinstance(raw, dict):
            raise TypeError("推理配置必须是 YAML 对象")
        try:
            timeout = raw["transport"]["timeout_seconds"]
            concurrency = raw["max_concurrency"]
        except KeyError as exc:
            raise ValueError(f"推理配置缺少必填字段: {exc}") from exc
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("transport.timeout_seconds 必须是有限正数")
        if type(concurrency) is not int or concurrency < 1:
            raise ValueError("max_concurrency 必须是正整数")
        roles = self._read_roles(raw.get("roles"))
        engine_type = get_inference_server()
        base_url = get_inference_gateway_url()
        impl = resolve_engine(engine_type)
        engine_options = raw.get("engine_options", {})
        if engine_options is None:
            engine_options = {}
        if not isinstance(engine_options, dict):
            raise TypeError("engine_options 必须是键值对")
        engines: dict[str, BaseInferenceService] = {}
        entries: dict[str, ModelEntry] = {}
        for role, config in roles.items():
            key = config["api_key"]
            if key not in engines:
                engines[key] = impl(
                    InferenceParams(
                        base_url=base_url,
                        timeout=float(timeout),
                        api_key=key,
                        extra=dict(engine_options),
                    )
                )
            entries[role] = ModelEntry(
                config["model_name"],
                config["options"],
                key,
                engine_type,
                engines[key],
                config["timeout_seconds"],
                config["context_window_tokens"],
            )
        self._config = InferenceConfig(concurrency, float(timeout), entries)
        return self._config

    @staticmethod
    def _read_roles(roles: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(roles, dict) or not roles:
            raise ValueError("推理配置缺少 roles 段")
        cleaned = {}
        for role, params in roles.items():
            if not isinstance(params, dict):
                raise TypeError(f"角色 '{role}' 配置格式错误")
            path = f"roles.{role}"
            api_key = params.get("api_key")
            if not isinstance(api_key, str) or not api_key.strip():
                raise ValueError(f"{path}.api_key 必须是非空字符串")
            name = params.get("model_name")
            options = params.get("options", {})
            if options is None:
                options = {}
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{path}.model_name 必须是非空字符串")
            if not isinstance(options, dict):
                raise TypeError(f"{path}.options 必须是键值对")
            role_timeout = params.get("timeout_seconds")
            context_window = params.get("context_window_tokens")
            if (role == "summary" or context_window is not None) and (
                type(context_window) is not int or context_window < 2
            ):
                raise ValueError(
                    f"{path}.context_window_tokens 必须是大于等于 2 的整数"
                )
            if role_timeout is not None and (
                isinstance(role_timeout, bool)
                or not isinstance(role_timeout, (int, float))
                or not math.isfinite(role_timeout)
                or role_timeout <= 0
            ):
                raise ValueError(f"{path}.timeout_seconds 必须是有限正数")
            if "max_tokens" in options and (
                type(options["max_tokens"]) is not int or options["max_tokens"] < 1
            ):
                raise ValueError(f"{path}.options.max_tokens 必须是正整数")
            for field, lower, upper in (("temperature", 0, 2), ("top_p", 0, 1)):
                if field in options:
                    value = options[field]
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or not lower <= value <= upper
                        or (field == "top_p" and value == 0)
                    ):
                        raise ValueError(f"{path}.options.{field} 超出有效数值范围")
            cleaned[role] = {
                "api_key": api_key,
                "model_name": name,
                "options": dict(options),
                "context_window_tokens": context_window,
                "timeout_seconds": float(role_timeout)
                if role_timeout is not None
                else None,
            }
        return cleaned
