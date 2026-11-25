# app-server/src/com/damon/ming/ai/rag/retriever/__init__.py
from src.com.damon.ming.ai.rag.retriever.base_retriever import BaseRetriever
from src.com.damon.ming.ai.rag.retriever.bm25_index import BM25Index
from src.com.damon.ming.ai.rag.retriever.hybrid_retriever import HybridRetriever
from src.com.damon.ming.ai.rag.retriever.rrf import ReciprocalRankFusion
from src.com.damon.ming.app.config.ai.rag.rag_runtime_config_loader import (
    RetrieverRuntimeConfig,
)


def create_retrievers(
    *,
    vector_store,
    embedder,
    bm25_index,
    retrieval_pool,
    runtime_config: RetrieverRuntimeConfig,
):
    """使用注入的配置创建共享 BM25 索引的检索器集合。"""
    from src.com.damon.ming.ai.rag.retriever.manager import RetrieverManager

    manager = RetrieverManager()
    manager.initialize(
        vector_store, embedder, bm25_index, retrieval_pool, runtime_config
    )
    return manager


__all__ = [
    "BM25Index",
    "BaseRetriever",
    "HybridRetriever",
    "ReciprocalRankFusion",
    "create_retrievers",
]
