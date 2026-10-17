import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.retriever.base_retriever import (
    DenseRetriever,
    SparseRetriever,
)
from src.com.damon.ming.ai.retriever.rrf import ReciprocalRankFusion
from src.com.damon.ming.log import pin


class HybridRetriever:
    """混合检索器：稠密 + 稀疏 + RRF（并发执行）。

    线程模型：
      - 不持有自己的线程池，由 RAGContainer 通过 retrieve() 的 executor 参数注入。
      - 稠密和稀疏检索通过注入的 executor 并发提交。
      - 取消由上层 RAGContainer 在 future 层面处理（取消后不再调用 retrieve）。

    纯业务逻辑：本类只做检索 + RRF 融合，不管理线程生命周期。
    """

    def __init__(
        self,
        dense_retriever: DenseRetriever,
        sparse_retriever: SparseRetriever,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        fuse_k: int = 60,
    ):
        self.dense_retriever = dense_retriever
        self.sparse_retriever = sparse_retriever
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.fuser = ReciprocalRankFusion(k=fuse_k)
        self._lock = threading.Lock()
        self.logger = pin("HybridRetriever")

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        dense_top_k: int = 50,
        sparse_top_k: int = 50,
        metadata_filter: dict[str, Any] | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> list[TextNode]:
        """
        混合检索主入口（并发执行稠密和稀疏检索）。

        Args:
            executor: 由 RAGContainer 注入的线程池。
                      不为 None 时，通过它并发执行稠密/稀疏检索；
                      None 时退化为串行执行（用于初始化等无池场景）。

        Returns:
            融合后的检索结果列表。
        """
        self.logger.info(f"[HybridRetriever] 开始混合检索 | query={query[:50]}...")

        if executor is not None:
            dense_future = executor.submit(
                self.dense_retriever.retrieve_with_score,
                query,
                dense_top_k,
                metadata_filter,
            )
            sparse_future = executor.submit(
                self.sparse_retriever.retrieve_with_score,
                query,
                sparse_top_k,
                metadata_filter,
            )

            dense_results: list = []
            sparse_results: list = []

            try:
                dense_results = dense_future.result(timeout=30)
                self.logger.info(
                    f"[HybridRetriever] 稠密检索完成 | 返回 {len(dense_results)} 个结果"
                )
            except Exception as e:
                self.logger.error(f"[HybridRetriever] 稠密检索失败: {e}")

            try:
                sparse_results = sparse_future.result(timeout=30)
                self.logger.info(
                    f"[HybridRetriever] 稀疏检索完成 | 返回 {len(sparse_results)} 个结果"
                )
            except Exception as e:
                self.logger.error(f"[HybridRetriever] 稀疏检索失败: {e}")
        else:
            # 无注入 executor：串行执行（初始化等场景）
            try:
                dense_results = self.dense_retriever.retrieve_with_score(
                    query, dense_top_k, metadata_filter
                )
            except Exception as e:
                self.logger.error(f"[HybridRetriever] 稠密检索失败: {e}")
                dense_results = []

            try:
                sparse_results = self.sparse_retriever.retrieve_with_score(
                    query, sparse_top_k, metadata_filter
                )
            except Exception as e:
                self.logger.error(f"[HybridRetriever] 稀疏检索失败: {e}")
                sparse_results = []

        # 如果都失败了，返回空
        if not dense_results and not sparse_results:
            self.logger.warning("[HybridRetriever] 所有检索都失败")
            return []

        # RRF 融合
        self.logger.info("[HybridRetriever] 执行 RRF 融合")
        fused_results = self.fuser.fuse_with_weights(
            results_list=[dense_results, sparse_results],
            weights=[self.dense_weight, self.sparse_weight],
            top_k=top_k,
        )

        self.logger.info(
            f"[HybridRetriever] 检索完成 | 返回 {len(fused_results)} 个结果"
        )
        return fused_results
