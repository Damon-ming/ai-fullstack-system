"""Reranker configuration owned and validated by the rerank module."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, kw_only=True)
class RerankerParams:
    """Validated initialization parameters consumed by a reranker engine."""

    model_name: str
    max_seq_len: int
    batch_size: int
    window_overlap: int
    max_windows_per_node: int
    include_heading: bool
    heading_prefix_template: str
    score_threshold: float | None = None
    device: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name 必须是非空字符串")
        if type(self.max_seq_len) is not int or self.max_seq_len <= 0:
            raise ValueError("max_seq_len 必须是正整数")
        if type(self.batch_size) is not int or self.batch_size <= 0:
            raise ValueError("batch_size 必须是正整数")
        if type(self.window_overlap) is not int or self.window_overlap < 0:
            raise ValueError("window_overlap 必须是非负整数")
        if type(self.max_windows_per_node) is not int or self.max_windows_per_node <= 0:
            raise ValueError("max_windows_per_node 必须是正整数")
        if not isinstance(self.include_heading, bool):
            raise TypeError("include_heading 必须是布尔值")
        if (
            not isinstance(self.heading_prefix_template, str)
            or "{heading_path}" not in self.heading_prefix_template
        ):
            raise ValueError(
                "heading_prefix_template 必须是包含 {heading_path} 的字符串"
            )
        if self.score_threshold is not None and (
            isinstance(self.score_threshold, bool)
            or not isinstance(self.score_threshold, (int, float))
            or not math.isfinite(self.score_threshold)
        ):
            raise ValueError("score_threshold 必须是有限数值或 None")
        if self.score_threshold is not None and not 0 <= self.score_threshold <= 1:
            raise ValueError("score_threshold 必须在 [0, 1] 范围内")


@dataclass(frozen=True, kw_only=True)
class RerankConfig:
    roles: dict[str, RerankerParams]

    def __post_init__(self) -> None:
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
        return cls(roles=roles)
