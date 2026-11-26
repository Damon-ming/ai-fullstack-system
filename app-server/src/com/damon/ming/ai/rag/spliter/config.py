"""Splitter configuration schema and YAML mapping parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class SplitterConfig:
    chunk_overlap: int
    max_grouped_chunks_per_section: int
    max_headed_chunks_per_section: int

    def __post_init__(self) -> None:
        if type(self.chunk_overlap) is not int or self.chunk_overlap < 0:
            raise ValueError("chunk_overlap 必须是非负整数")
        if (
            type(self.max_grouped_chunks_per_section) is not int
            or self.max_grouped_chunks_per_section <= 0
        ):
            raise ValueError("max_grouped_chunks_per_section 必须是正整数")
        if (
            type(self.max_headed_chunks_per_section) is not int
            or self.max_headed_chunks_per_section <= 0
        ):
            raise ValueError("max_headed_chunks_per_section 必须是正整数")

    @classmethod
    def from_mapping(cls, raw: Any) -> SplitterConfig:
        if not isinstance(raw, dict):
            raise TypeError("RAG splitter 配置必须是键值对象")
        try:
            return cls(
                chunk_overlap=(
                    0 if raw.get("chunk_overlap") is None else raw["chunk_overlap"]
                ),
                max_grouped_chunks_per_section=raw["max_grouped_chunks_per_section"],
                max_headed_chunks_per_section=raw["max_headed_chunks_per_section"],
            )
        except KeyError as exc:
            raise ValueError(f"分割器配置缺少必填字段: {exc}") from exc
