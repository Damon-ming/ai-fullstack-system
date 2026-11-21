"""
分割器配置加载器 —— 从 YAML 读取 StructuredDocumentSplitter 构造参数。

用法：
  loader = SplitterConfigLoader()
  config = loader.load()
  config.max_chunk_token_size
  config.chunk_overlap
"""

import os

from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class SplitterConfig:
    """StructuredDocumentSplitter 配置参数。

    max_chunk_token_size 必填；chunk_overlap 省略或为 null 时按 0 处理。
    """

    __slots__ = (
        "chunk_overlap",
        "max_chunk_token_size",
    )

    def __init__(
        self,
        max_chunk_token_size: int,
        chunk_overlap: int | None = None,
    ):
        if type(max_chunk_token_size) is not int or max_chunk_token_size <= 0:
            raise ValueError("max_chunk_token_size 必须是正整数")
        if chunk_overlap is None:
            chunk_overlap = 0
        if (
            type(chunk_overlap) is not int
            or not 0 <= chunk_overlap < max_chunk_token_size
        ):
            raise ValueError("chunk_overlap 必须是小于 max_chunk_token_size 的非负整数")
        self.max_chunk_token_size = max_chunk_token_size
        self.chunk_overlap = chunk_overlap


class SplitterConfigLoader:
    """从 YAML 文件加载分割器配置，返回 SplitterConfig 实例。"""

    def __init__(self, config_path: str | None = None):
        self._cache: SplitterConfig | None = None
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )

    def load(self) -> SplitterConfig:
        if self._cache is None:
            self._cache = self._build()
        return self._cache

    # ---- 私有 -------------------------------------------------------------

    def _build(self) -> SplitterConfig:
        raw = self._read_yaml()
        try:
            return SplitterConfig(
                max_chunk_token_size=raw["max_chunk_token_size"],
                chunk_overlap=raw.get("chunk_overlap"),
            )
        except KeyError as e:
            raise ValueError(f"分割器配置缺少必填字段: {e}") from e

    def _read_yaml(self) -> dict:
        raw_cfg = load_yaml(self._config_path)

        if not isinstance(raw_cfg, dict):
            raise TypeError("分割器配置必须是 YAML 对象")
        return raw_cfg
