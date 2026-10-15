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
    """
    混合检索器：稠密 + 稀疏 + RRF（并发执行）
    仅负责多路召回与融合，Rerank由外部独立模块实现
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
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="HybridRetriever"
        )
        self._lock = threading.Lock()
        self.logger = pin("HybridRetriever")

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        dense_top_k: int = 50,
        sparse_top_k: int = 50,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[TextNode]:
        """
        混合检索主入口（并发执行稠密和稀疏检索）
        """
        self.logger.info(f"[HybridRetriever] 开始混合检索 | query={query[:50]}...")

        # 提交两个检索任务到线程池，并发执行
        dense_future = self._executor.submit(
            self.dense_retriever.retrieve_with_score,
            query,
            dense_top_k,
            metadata_filter,
        )

        sparse_future = self._executor.submit(
            self.sparse_retriever.retrieve_with_score,
            query,
            sparse_top_k,
            metadata_filter,
        )

        # 等待两个任务完成（并发执行）
        dense_results = []
        sparse_results = []

        try:
            dense_results = dense_future.result(timeout=30)  # 30秒超时保护
            self.logger.info(
                f"[HybridRetriever] 稠密检索完成 | 返回 {len(dense_results)} 个结果"
            )
        except Exception as e:
            self.logger.error(f"[HybridRetriever] 稠密检索失败: {e}")
            dense_results = []

        try:
            sparse_results = sparse_future.result(timeout=30)
            self.logger.info(
                f"[HybridRetriever] 稀疏检索完成 | 返回 {len(sparse_results)} 个结果"
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

    def __del__(self):
        """清理线程池"""
        if hasattr(self, "_executor"):
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self.logger.info("[HybridRetriever] 线程池已关闭")
            except Exception:
                pass  # 析构时避免抛出异常
