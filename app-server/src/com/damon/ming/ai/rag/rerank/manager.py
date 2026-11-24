"""RAG 重排模型的初始化和访问入口。"""

from pathlib import Path

from src.com.damon.ming.ai.rag.rerank.base_reranker import BaseReranker
from src.com.damon.ming.ai.rag.rerank.config.rerank_config_loader import (
    RerankerConfigLoader,
)


class RerankersManager:
    def __init__(self) -> None:
        self._reranker: BaseReranker | None = None

    def initialize(self, model_root_dir: Path) -> None:
        if self._reranker is not None:
            raise RuntimeError("RAG 重排器已经初始化")
        from src.com.damon.ming.ai.rag.rerank import list_engines
        from src.com.damon.ming.log import pin

        engines = list_engines()
        if engines:
            pin("RerankersManager").info("[Registry] 可用重排引擎: %s", engines)
        else:
            pin("RerankersManager").warning("[Registry] 未注册任何重排引擎")
        self._reranker = RerankerConfigLoader().load(
            "bge_reranker_v2_m3", model_root_dir
        )

    def get_bge_reranker_v2_m3(self) -> BaseReranker:
        if self._reranker is None:
            raise RuntimeError("RAG 重排器尚未初始化")
        return self._reranker
