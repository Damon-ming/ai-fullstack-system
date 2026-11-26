"""Reranker configuration owned and validated by the rerank module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.ai.rag.rerank.params import RerankerParams


@dataclass(frozen=True, kw_only=True)
class RerankConfig:
    model_dir: str
    roles: dict[str, RerankerParams]

    def __post_init__(self) -> None:
        if not isinstance(self.model_dir, str) or not self.model_dir.strip():
            raise ValueError("RAG rerank.model_dir 必须是非空字符串")
        if not isinstance(self.roles, dict) or not self.roles:
            raise ValueError("RAG rerank 配置必须包含至少一个 role")
        if not all(
            isinstance(params, RerankerParams) for params in self.roles.values()
        ):
            raise TypeError("RAG rerank roles 必须使用 RerankerParams")

    @classmethod
    def from_mapping(cls, raw: Any) -> RerankConfig:
        if not isinstance(raw, dict):
            raise TypeError("RAG rerank 配置必须是键值对象")
        raw_roles = raw.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("RAG rerank 配置缺少 roles")

        known_fields = set(RerankerParams.__dataclass_fields__)
        roles: dict[str, RerankerParams] = {}
        for name, values in raw_roles.items():
            if not isinstance(values, dict):
                raise TypeError(f"重排器配置 '{name}' 必须是键值对象")
            base_kwargs = {
                key: value for key, value in values.items() if key in known_fields
            }
            extra_kwargs = {
                key: value for key, value in values.items() if key not in known_fields
            }
            try:
                roles[name] = RerankerParams(**base_kwargs, extra=extra_kwargs)
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"重排器配置 '{name}' 无效: {exc}") from exc
        return cls(model_dir=raw.get("model_dir"), roles=roles)
