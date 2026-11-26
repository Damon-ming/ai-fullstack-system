"""Summary configuration schema and YAML mapping parser."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class SummaryConfig:
    system_prompt_template: str
    context_message_template: str
    context_margin_ratio: float | None
    context_overlap_ratio: float | None

    def __post_init__(self) -> None:
        if self.context_margin_ratio is not None:
            value = self.context_margin_ratio
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise TypeError("summary.context_margin_ratio 必须是有限数值或 null")
            if not 0 <= value < 1:
                raise ValueError("summary.context_margin_ratio 必须大于等于 0 且小于 1")
        if self.context_overlap_ratio is not None:
            value = self.context_overlap_ratio
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise TypeError("summary.context_overlap_ratio 必须是有限数值或 null")
            if not 0 <= value < 0.5:
                raise ValueError(
                    "summary.context_overlap_ratio 必须大于等于 0 且小于 0.5"
                )
        if (
            not isinstance(self.context_message_template, str)
            or not self.context_message_template.strip()
        ):
            raise ValueError("summary.context_message_template 必须是非空字符串")
        if any(
            token not in self.context_message_template
            for token in ("{context}", "{content}")
        ):
            raise ValueError(
                "summary.context_message_template 必须包含 {context} 和 {content}"
            )
        if (
            not isinstance(self.system_prompt_template, str)
            or not self.system_prompt_template.strip()
        ):
            raise ValueError("summary.system_prompt_template 必须是非空字符串")
        if "{max_tokens}" not in self.system_prompt_template:
            raise ValueError("summary.system_prompt_template 必须包含 {max_tokens}")

    @classmethod
    def from_mapping(cls, raw: Any) -> SummaryConfig:
        if not isinstance(raw, dict):
            raise TypeError("RAG summary 配置必须是键值对象")
        return cls(
            system_prompt_template=raw.get("system_prompt_template"),
            context_message_template=raw.get("context_message_template"),
            context_margin_ratio=raw.get("context_margin_ratio"),
            context_overlap_ratio=raw.get("context_overlap_ratio"),
        )
