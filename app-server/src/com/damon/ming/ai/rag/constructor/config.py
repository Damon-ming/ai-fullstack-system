# app-server/src/com/damon/ming/ai/rag/constructor/config.py
"""Configuration contract for RAG section reconstruction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ConstructorConfig:
    """Formatting rules used when reconstructed sections are sent to the model."""

    source_label_template: str
    heading_label_template: str
    heading_separator: str

    def __post_init__(self) -> None:
        for name, value in (
            ("source_label_template", self.source_label_template),
            ("heading_label_template", self.heading_label_template),
        ):
            if not isinstance(value, str) or "{value}" not in value:
                raise ValueError(f"{name} 必须是包含 {{value}} 的字符串")
        if not isinstance(self.heading_separator, str) or not self.heading_separator:
            raise ValueError("heading_separator 必须是非空字符串")

    @classmethod
    def from_mapping(cls, raw: Any) -> ConstructorConfig:
        """Validate the constructor section from the runtime YAML mapping."""
        if not isinstance(raw, dict):
            raise TypeError("constructor 配置必须是键值对象")
        templates: dict[str, str] = {}
        for key in ("source_label_template", "heading_label_template"):
            value = raw.get(key)
            if not isinstance(value, str) or "{value}" not in value:
                raise ValueError(f"constructor.{key} 必须是包含 {{value}} 的字符串")
            templates[key] = value
        heading_separator = raw.get("heading_separator")
        if not isinstance(heading_separator, str) or not heading_separator:
            raise ValueError("constructor.heading_separator 必须是非空字符串")
        return cls(
            source_label_template=templates["source_label_template"],
            heading_label_template=templates["heading_label_template"],
            heading_separator=heading_separator,
        )
