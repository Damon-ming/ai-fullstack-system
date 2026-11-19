"""
分割器配置加载器 —— 从 YAML 读取 MarkdownDocumentSplitter 构造参数。

用法：
  loader = SplitterConfigLoader()
  configs = loader.load_all()          # dict[str, SplitterConfig]
  configs["primary"].max_chunk_token_size
  configs["primary"].chunk_overlap
"""

import os

import yaml


class SplitterConfig:
    """MarkdownDocumentSplitter 配置参数。

    所有参数无默认值，必须由 YAML 显式提供。
    """

    __slots__ = (
        "chunk_overlap",
        "max_chunk_token_size",
        "name",
    )

    def __init__(
        self,
        name: str,
        max_chunk_token_size: int,
        chunk_overlap: int,
    ):
        self.name = name
        self.max_chunk_token_size = max_chunk_token_size
        self.chunk_overlap = chunk_overlap


class SplitterConfigLoader:
    """从 YAML 文件加载分割器配置，返回 SplitterConfig 实例。"""

    def __init__(self, config_path: str | None = None):
        self._cache: dict[str, SplitterConfig] = {}
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "splitter-config.yaml")
        self._config_path = config_path

    def load_all(self) -> dict[str, SplitterConfig]:
        if self._cache:
            return self._cache

        for name in self._list_names():
            self._cache[name] = self._build_one(name)
        return self._cache

    def load(self, name: str) -> SplitterConfig:
        if name in self._cache:
            return self._cache[name]

        config = self._build_one(name)
        self._cache[name] = config
        return config

    # ---- 私有 -------------------------------------------------------------

    def _list_names(self) -> list[str]:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"分割器配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or "splitters" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'splitters' 根节点")
        return list(raw_cfg["splitters"].keys())

    def _build_one(self, name: str) -> SplitterConfig:
        raw = self._read_yaml(name)
        try:
            return SplitterConfig(
                name=name,
                max_chunk_token_size=raw["max_chunk_token_size"],
                chunk_overlap=raw["chunk_overlap"],
            )
        except KeyError as e:
            raise ValueError(f"分割器配置 '{name}' 缺少必填字段: {e}") from e

    def _read_yaml(self, name: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"分割器配置文件不存在: {self._config_path}")

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)

        if raw_cfg is None or "splitters" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'splitters' 根节点")

        section = raw_cfg["splitters"]
        if name not in section:
            raise ValueError(
                f"未找到分割器配置: '{name}'. 可用: {list(section.keys())}"
            )
        return section[name]
