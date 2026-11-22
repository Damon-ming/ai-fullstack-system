"""RAG 重排模型的初始化和访问入口。"""

from pathlib import Path

from src.com.damon.ming.ai.rag.rerank.base_reranker import BaseReranker
from src.com.damon.ming.ai.rag.rerank.config.rerank_config_loader import (
    RerankerConfigLoader,
)


class RagRerankers:
    def __init__(self) -> None:
        self._items: dict[str, BaseReranker] | None = None

    def initialize(self, model_root_dir: Path) -> None:
        if self._items is not None:
            raise RuntimeError("RAG 重排器已经初始化")
        from src.com.damon.ming.ai.rag.rerank import list_engines
        from src.com.damon.ming.log import pin

        engines = list_engines()
        if engines:
            pin("RerankRegistry").info("[Registry] 可用重排引擎: %s", engines)
        else:
            pin("RerankRegistry").warning("[Registry] 未注册任何重排引擎")
        self._items = RerankerConfigLoader().load_all(model_root_dir)

    def get_zh_primary(self) -> BaseReranker:
        if self._items is None:
            raise RuntimeError("RAG 重排器尚未初始化")
        try:
            return self._items["zh_primary"]
        except KeyError as exc:
            raise ValueError("缺少 RAG 重排器配置: zh_primary") from exc
