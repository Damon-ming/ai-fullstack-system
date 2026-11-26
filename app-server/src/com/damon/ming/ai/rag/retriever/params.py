"""Validated runtime parameters for RAG retrievers."""

from __future__ import annotations

import math
from dataclasses import dataclass


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
