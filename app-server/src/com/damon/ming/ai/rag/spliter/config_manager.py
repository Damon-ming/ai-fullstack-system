"""分割器配置的初始化和访问入口。"""

from src.com.damon.ming.ai.rag.config.splitter.splitter_config_loader import (
    SplitterConfig,
    SplitterConfigLoader,
)


class RagSplitterConfigs:
    def __init__(self) -> None:
        self._items: dict[str, SplitterConfig] | None = None

    def initialize(self) -> None:
        if self._items is not None:
            raise RuntimeError("RAG 分割器已经初始化")
        self._items = SplitterConfigLoader().load_all()

    def get_common(self) -> SplitterConfig:
        if self._items is None:
            raise RuntimeError("RAG 分割器尚未初始化")
        try:
            return self._items["common"]
        except KeyError as exc:
            raise ValueError("缺少 RAG 分割器配置: common") from exc
