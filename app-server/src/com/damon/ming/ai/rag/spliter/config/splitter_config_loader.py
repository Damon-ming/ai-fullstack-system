"""分割器策略配置加载器。"""

import os

from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class SplitterConfig:
    __slots__ = (
        "chunk_overlap",
        "max_grouped_chunks_per_section",
        "max_headed_chunks_per_section",
    )

    def __init__(
        self,
        max_grouped_chunks_per_section: int,
        max_headed_chunks_per_section: int,
        chunk_overlap: int | None = None,
    ):
        if chunk_overlap is None:
            chunk_overlap = 0
        if type(chunk_overlap) is not int or chunk_overlap < 0:
            raise ValueError("chunk_overlap 必须是非负整数")
        if (
            type(max_grouped_chunks_per_section) is not int
            or max_grouped_chunks_per_section <= 0
        ):
            raise ValueError("max_grouped_chunks_per_section 必须是正整数")
        if (
            type(max_headed_chunks_per_section) is not int
            or max_headed_chunks_per_section <= 0
        ):
            raise ValueError("max_headed_chunks_per_section 必须是正整数")
        self.chunk_overlap = chunk_overlap
        self.max_grouped_chunks_per_section = max_grouped_chunks_per_section
        self.max_headed_chunks_per_section = max_headed_chunks_per_section


class SplitterConfigLoader:
    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )

    def load(self) -> SplitterConfig:
        raw = load_yaml(self._config_path)
        if not isinstance(raw, dict):
            raise TypeError("分割器配置必须是 YAML 对象")
        try:
            return SplitterConfig(
                chunk_overlap=raw.get("chunk_overlap"),
                max_grouped_chunks_per_section=raw["max_grouped_chunks_per_section"],
                max_headed_chunks_per_section=raw["max_headed_chunks_per_section"],
            )
        except KeyError as exc:
            raise ValueError(f"分割器配置缺少必填字段: {exc}") from exc
