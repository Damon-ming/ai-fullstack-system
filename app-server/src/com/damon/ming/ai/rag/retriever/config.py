"""Retriever configuration schema and YAML mapping parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.ai.rag.retriever.params import RetrieverRoleParams


@dataclass(frozen=True, kw_only=True)
class RetrieverConfig:
    roles: dict[str, RetrieverRoleParams]

    def __post_init__(self) -> None:
        if not isinstance(self.roles, dict) or not self.roles:
            raise ValueError("RAG retriever 配置缺少 roles")
        if "hybrid" not in self.roles:
            raise ValueError("RAG retriever 配置缺少 hybrid role")

    @classmethod
    def from_mapping(cls, raw: Any) -> RetrieverConfig:
        if not isinstance(raw, dict):
            raise TypeError("RAG retriever 配置必须是键值对象")
        raw_roles = raw.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("RAG retriever 配置缺少 roles")

        roles: dict[str, RetrieverRoleParams] = {}
        for name, section in raw_roles.items():
            if not isinstance(section, dict):
                raise TypeError(f"检索器配置 '{name}' 必须是键值对象")
            params = section.get("params", {})
            if not isinstance(params, dict):
                raise TypeError(f"检索器配置 '{name}' 的 params 必须是键值对象")
            try:
                roles[name] = RetrieverRoleParams(
                    name=name,
                    retrieve_top_k=section["retrieve_top_k"],
                    dense_top_k=section["dense_top_k"],
                    sparse_top_k=section["sparse_top_k"],
                    dedup_by_section=section["dedup_by_section"],
                    dense_weight=section["dense_weight"],
                    sparse_weight=section["sparse_weight"],
                    fuse_k=section["fuse_k"],
                    retrieval_timeout_seconds=section["retrieval_timeout_seconds"],
                    max_section_oversample_multiplier=params[
                        "max_section_oversample_multiplier"
                    ],
                    rrf_oversample_multiplier=params["rrf_oversample_multiplier"],
                )
            except KeyError as exc:
                raise ValueError(f"检索器配置 '{name}' 缺少必填字段: {exc}") from exc
        return cls(roles=roles)
