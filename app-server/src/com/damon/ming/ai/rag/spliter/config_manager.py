# app-server/src/com/damon/ming/ai/rag/spliter/config_manager.py
"""分割器配置的初始化和访问入口。"""

from src.com.damon.ming.ai.rag.spliter.config.splitter_config_loader import (
    SplitterConfig,
    SplitterConfigLoader,
)


class RagSplitterConfigs:
    def __init__(self) -> None:
        self._config: SplitterConfig | None = None

    def initialize(self) -> None:
        if self._config is not None:
            raise RuntimeError("RAG 分割器已经初始化")
        self._config = SplitterConfigLoader().load()

    def get(self) -> SplitterConfig:
        if self._config is None:
            raise RuntimeError("RAG 分割器尚未初始化")
        return self._config
