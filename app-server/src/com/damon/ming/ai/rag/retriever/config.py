"""Retriever configuration schema and YAML mapping parser."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class RetrieverRoleParams:
    name: str
    top_k: int
    retrieve_top_k: int
    dense_top_k: int
    sparse_top_k: int
    dedup_by_section: bool
    dense_weight: float
    sparse_weight: float
    fuse_k: int
    retrieval_timeout_seconds: float
    max_section_oversample_multiplier: int
    rrf_oversample_multiplier: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("retriever role 名称不能为空")
        for name in (
            "top_k",
            "retrieve_top_k",
            "dense_top_k",
            "sparse_top_k",
            "fuse_k",
            "max_section_oversample_multiplier",
            "rrf_oversample_multiplier",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"retriever.{self.name}.{name} 必须是正整数")
        if not isinstance(self.dedup_by_section, bool):
            raise TypeError(f"retriever.{self.name}.dedup_by_section 必须是布尔值")
        for name in ("dense_weight", "sparse_weight", "retrieval_timeout_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                or (name == "retrieval_timeout_seconds" and value == 0)
            ):
                constraint = (
                    "有限正数" if name == "retrieval_timeout_seconds" else "有限非负数"
                )
                raise ValueError(f"retriever.{self.name}.{name} 必须是{constraint}")
        if self.dense_weight == 0 and self.sparse_weight == 0:
            raise ValueError("dense_weight 和 sparse_weight 不能同时为 0")


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
                    top_k=section["top_k"],
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
