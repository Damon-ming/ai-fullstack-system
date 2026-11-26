"""YAML configuration for RAG embedding."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


# todo: 太多config看下怎么解决
@dataclass(frozen=True, kw_only=True)
class EmbeddingTransportConfig:
    timeout_seconds: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("Embedding transport.timeout_seconds 必须是有限正数")


@dataclass(frozen=True, kw_only=True)
class EmbeddingRoleConfig:
    """A role's YAML settings for both embedding behavior and gateway access."""

    model_name: str
    api_key: str
    query_prefix: str
    passage_prefix: str
    batch_size: int
    max_input_tokens: int
    dimension: int
    max_model_len: int

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name 必须是非空字符串")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key 必须是非空字符串")
        if type(self.batch_size) is not int or self.batch_size <= 0:
            raise ValueError("batch_size 必须是正整数")
        if not isinstance(self.query_prefix, str) or not isinstance(
            self.passage_prefix, str
        ):
            raise TypeError("文本前缀必须是字符串")
        for name, value in (
            ("max_input_tokens", self.max_input_tokens),
            ("dimension", self.dimension),
            ("max_model_len", self.max_model_len),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} 必须是正整数")
        if self.max_input_tokens > self.max_model_len:
            raise ValueError("max_input_tokens 不能大于 max-model-len")


@dataclass(frozen=True, kw_only=True)
class EmbeddingConfig:
    """Parsed mapping of the embedding section in rag-runtime.yaml."""

    transport: EmbeddingTransportConfig
    roles: dict[str, EmbeddingRoleConfig]

    def __post_init__(self) -> None:
        if not isinstance(self.transport, EmbeddingTransportConfig):
            raise TypeError("RAG embedding transport 必须使用 EmbeddingTransportConfig")
        if not isinstance(self.roles, dict) or not self.roles:
            raise ValueError("RAG embedding 配置缺少 roles")
        if not all(
            isinstance(config, EmbeddingRoleConfig) for config in self.roles.values()
        ):
            raise TypeError("RAG embedding roles 必须使用 EmbeddingRoleConfig")

    @classmethod
    def from_mapping(cls, raw: Any) -> EmbeddingConfig:
        if not isinstance(raw, dict):
            raise TypeError("RAG embedding 配置必须是 YAML 对象")
        transport_raw = raw.get("transport")
        if not isinstance(transport_raw, dict):
            raise TypeError("Embedding 配置缺少 transport")
        roles_raw = raw.get("roles")
        if not isinstance(roles_raw, dict) or not roles_raw:
            raise ValueError("RAG embedding 配置缺少 roles")

        transport = EmbeddingTransportConfig(
            timeout_seconds=transport_raw.get("timeout_seconds")
        )
        roles: dict[str, EmbeddingRoleConfig] = {}
        for role, entry in roles_raw.items():
            if not isinstance(entry, dict):
                raise TypeError(f"Embedding role '{role}' 配置必须是 YAML 对象")
            try:
                roles[role] = EmbeddingRoleConfig(
                    model_name=entry.get("model_name"),
                    api_key=entry.get("api_key"),
                    query_prefix=entry.get("query_prefix", ""),
                    passage_prefix=entry.get("passage_prefix", ""),
                    batch_size=entry.get("batch_size"),
                    max_input_tokens=entry.get("max_input_tokens"),
                    dimension=entry.get("dimension"),
                    max_model_len=entry.get("max_model_len"),
                )
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"Embedding role '{role}' 配置无效: {exc}") from exc
        return cls(transport=transport, roles=roles)
