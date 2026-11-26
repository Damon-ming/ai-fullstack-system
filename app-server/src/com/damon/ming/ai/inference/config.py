"""映射 inference YAML 并构造内部角色参数。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.ai.inference.params import InferenceRoleParams


@dataclass(frozen=True, kw_only=True)
class InferenceConfig:
    max_concurrency: int
    timeout_seconds: float
    engine_options: dict[str, Any]
    roles: dict[str, InferenceRoleParams]

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("transport.timeout_seconds 必须是有限正数")
        if type(self.max_concurrency) is not int or self.max_concurrency < 1:
            raise ValueError("max_concurrency 必须是正整数")
        if not isinstance(self.engine_options, dict):
            raise TypeError("engine_options 必须是键值对")
        if not isinstance(self.roles, dict) or not self.roles:
            raise ValueError("推理配置缺少 roles 段")
        if not all(
            isinstance(role, InferenceRoleParams) for role in self.roles.values()
        ):
            raise TypeError("推理 roles 必须使用 InferenceRoleParams")

    @classmethod
    def from_mapping(cls, raw: Any) -> InferenceConfig:
        if not isinstance(raw, dict):
            raise TypeError("推理配置必须是 YAML 对象")
        transport = raw.get("transport")
        if not isinstance(transport, dict):
            raise TypeError("推理配置缺少 transport 段")
        raw_roles = raw.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("推理配置缺少 roles 段")
        roles: dict[str, InferenceRoleParams] = {}
        for name, values in raw_roles.items():
            if not isinstance(values, dict):
                raise TypeError(f"角色 '{name}' 配置格式错误")
            options = values.get("options")
            if options is None:
                options = {}
            if not isinstance(options, dict):
                raise TypeError(f"roles.{name}.options 必须是键值对")
            try:
                roles[name] = InferenceRoleParams(
                    model_name=values.get("model_name"),
                    api_key=values.get("api_key"),
                    options=dict(options),
                    timeout_seconds=values.get("timeout_seconds"),
                    max_model_len=values.get("max_model_len"),
                )
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"roles.{name} 配置无效: {exc}") from exc
        engine_options = raw.get("engine_options")
        if engine_options is None:
            engine_options = {}
        if not isinstance(engine_options, dict):
            raise TypeError("engine_options 必须是键值对")
        return cls(
            max_concurrency=raw.get("max_concurrency"),
            timeout_seconds=transport.get("timeout_seconds"),
            engine_options=dict(engine_options),
            roles=roles,
        )
