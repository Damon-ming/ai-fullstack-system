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
from src.com.damon.ming.ai.rag.retriever.config import (
    RetrieverConfig,
    RetrieverRoleParams,
)
from src.com.damon.ming.ai.rag.retriever.hybrid_retriever import HybridRetriever
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore


class RetrieverManager:
    """使用注入的配置装配稠密、稀疏和混合检索器。"""

    def __init__(self) -> None:
        self._config: RetrieverRoleParams | None = None
        self._dense: DenseRetriever | None = None
        self._sparse: SparseRetriever | None = None
        self._hybrid: HybridRetriever | None = None

    def initialize(
        self,
        vector_store: BaseVectorStore,
        embedder: BaseEmbeddingService,
        bm25_index: BM25Index,
        retrieval_pool: ThreadPoolExecutor,
        config_mapping: dict[str, object],
    ) -> None:
        if self._hybrid is not None:
            raise RuntimeError("RAG 检索器已经初始化")
        try:
            config = RetrieverConfig.from_mapping(config_mapping)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"RAG retriever 配置无效: {exc}") from exc
        role_params = config.roles["hybrid"]
        dense = DenseRetriever(vector_store=vector_store, embedding_service=embedder)
        sparse = SparseRetriever(bm25_index=bm25_index)
        hybrid = HybridRetriever(
            dense_retriever=dense,
            sparse_retriever=sparse,
            dense_weight=role_params.dense_weight,
            sparse_weight=role_params.sparse_weight,
            fuse_k=role_params.fuse_k,
            max_section_oversample_multiplier=role_params.max_section_oversample_multiplier,
            rrf_oversample_multiplier=role_params.rrf_oversample_multiplier,
            retrieval_timeout_seconds=role_params.retrieval_timeout_seconds,
            retrieval_pool=retrieval_pool,
        )
        self._config = role_params
        self._dense = dense
        self._sparse = sparse
        self._hybrid = hybrid

    def get_hybrid_config(self) -> RetrieverRoleParams:
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
