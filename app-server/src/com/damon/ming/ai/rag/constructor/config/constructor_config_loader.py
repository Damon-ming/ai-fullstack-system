"""加载章节重建的参考资料标签格式。"""

from dataclasses import dataclass
from pathlib import Path

from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


@dataclass(frozen=True)
class ConstructorConfig:
    source_label_template: str
    heading_label_template: str
    heading_separator: str


class ConstructorConfigLoader:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else Path(__file__).parent
        )

    def load(self) -> ConstructorConfig:
        raw = load_yaml(self._config_path)
        templates = {}
        for key in ("source_label_template", "heading_label_template"):
            value = raw.get(key)
            if not isinstance(value, str) or "{value}" not in value:
                raise ValueError(f"constructor.{key} 必须是包含 {{value}} 的字符串")
            templates[key] = value

        heading_separator = raw.get("heading_separator")
        if not isinstance(heading_separator, str) or not heading_separator:
            raise ValueError("constructor.heading_separator 必须是非空字符串")

        return ConstructorConfig(
            source_label_template=templates["source_label_template"],
            heading_label_template=templates["heading_label_template"],
            heading_separator=heading_separator,
        )
