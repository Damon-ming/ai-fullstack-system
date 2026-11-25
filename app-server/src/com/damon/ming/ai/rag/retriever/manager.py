"""初始化和访问使用同一 BM25 索引的 RAG 检索器。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.retriever.base_retriever import (
    DenseRetriever,
    SparseRetriever,
)
from src.com.damon.ming.ai.rag.retriever.bm25_index import BM25Index
from src.com.damon.ming.ai.rag.retriever.hybrid_retriever import HybridRetriever
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.app.config.ai.rag.rag_runtime_config_loader import (
    RetrieverConfig,
    RetrieverRuntimeConfig,
)


class RetrieverManager:
    """使用注入的配置装配稠密、稀疏和混合检索器。"""

    def __init__(self) -> None:
        self._config: RetrieverConfig | None = None
        self._dense: DenseRetriever | None = None
        self._sparse: SparseRetriever | None = None
        self._hybrid: HybridRetriever | None = None

    def initialize(
        self,
        vector_store: BaseVectorStore,
        embedder: BaseEmbeddingService,
        bm25_index: BM25Index,
        retrieval_pool: ThreadPoolExecutor,
        runtime_config: RetrieverRuntimeConfig,
    ) -> None:
        if self._hybrid is not None:
            raise RuntimeError("RAG 检索器已经初始化")
        try:
            config = runtime_config.roles["hybrid"]
        except KeyError as exc:
            raise ValueError("RAG retriever 配置缺少 hybrid role") from exc
        dense = DenseRetriever(vector_store=vector_store, embedding_service=embedder)
        sparse = SparseRetriever(bm25_index=bm25_index)
        hybrid = HybridRetriever(
            dense_retriever=dense,
            sparse_retriever=sparse,
            dense_weight=config.dense_weight,
            sparse_weight=config.sparse_weight,
            fuse_k=config.fuse_k,
            max_section_oversample_multiplier=config.max_section_oversample_multiplier,
            rrf_oversample_multiplier=config.rrf_oversample_multiplier,
            retrieval_timeout_seconds=config.retrieval_timeout_seconds,
            retrieval_pool=retrieval_pool,
        )
        self._config = config
        self._dense = dense
        self._sparse = sparse
        self._hybrid = hybrid

    def get_hybrid_config(self) -> RetrieverConfig:
        if self._config is None:
            raise RuntimeError("RAG 检索器尚未初始化")
        return self._config

    def get_dense(self) -> DenseRetriever:
        if self._dense is None:
            raise RuntimeError("RAG 检索器尚未初始化")
        return self._dense

    def get_sparse(self) -> SparseRetriever:
        if self._sparse is None:
            raise RuntimeError("RAG 检索器尚未初始化")
        return self._sparse

    def get_hybrid(self) -> HybridRetriever:
        if self._hybrid is None:
            raise RuntimeError("RAG 检索器尚未初始化")
        return self._hybrid
