"""Runtime parameters consumed by reranker implementations."""

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
