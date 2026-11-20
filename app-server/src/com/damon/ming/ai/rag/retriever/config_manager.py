"""检索器配置的初始化和访问入口。"""

from src.com.damon.ming.ai.rag.retriever.config.retriever_config_loader import (
    RetrieverConfig,
    RetrieverConfigLoader,
)


class RagRetrieverConfigs:
    def __init__(self) -> None:
        self._items: dict[str, RetrieverConfig] | None = None

    def initialize(self) -> None:
        if self._items is not None:
            raise RuntimeError("RAG 检索器已经初始化")
        self._items = RetrieverConfigLoader().load_all()

    def get_common(self) -> RetrieverConfig:
        if self._items is None:
            raise RuntimeError("RAG 检索器尚未初始化")
        try:
            return self._items["common"]
        except KeyError as exc:
            raise ValueError("缺少 RAG 检索器配置: common") from exc
