from concurrent.futures import ThreadPoolExecutor
from typing import Any

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.retriever.base_retriever import (
    BaseRetriever,
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

    多样性保证（由 dedup_by_section 开关控制）：
      True：Dense/Sparse 各自去重 + RRF 后去重 + 循环扩大，尽力填满 top_k。
      False：跳过所有 section 去重和循环扩大，直接返回 RRF 原始结果。

    注意：dedup_by_section / dense_top_k / sparse_top_k 无默认值，调用方必须显式传入。
          max_section_oversample_multiplier / rrf_oversample_multiplier 为构造参数。
    """

    def __init__(
        self,
        dense_retriever: DenseRetriever,
        sparse_retriever: SparseRetriever,
        dense_weight: float,
        sparse_weight: float,
        fuse_k: int,
        max_section_oversample_multiplier: int,
        rrf_oversample_multiplier: int,
    ):
        self.dense_retriever = dense_retriever
        self.sparse_retriever = sparse_retriever
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.fuser = ReciprocalRankFusion(k=fuse_k)
        self.max_section_oversample_multiplier = max_section_oversample_multiplier
        self.rrf_oversample_multiplier = rrf_oversample_multiplier
        self.logger = pin("HybridRetriever")

    def retrieve(
        self,
        query: str,
        top_k: int,
        dedup_by_section: bool,
        dense_top_k: int,
        sparse_top_k: int,
        metadata_filter: dict[str, Any] | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> list[TextNode]:
        """
        混合检索主入口（并发执行稠密和稀疏检索）。

        Args:
            query: 查询文本。
            top_k: 返回结果数量上限。
            dedup_by_section: True 时保证 section 多样性并尽力填满 top_k；
                              False 时跳过所有 section 去重，直接返回 RRF 原始结果。
                              必须显式传入，无默认值。
            dense_top_k: 稠密检索候选数。
            sparse_top_k: 稀疏检索候选数。
            metadata_filter: 元数据过滤条件。
            executor: 由 RAGContainer 注入的线程池。

        Returns:
            融合后的检索结果列表。
        """
        self.logger.info(
            f"[HybridRetriever] 开始混合检索 | query={query[:50]} | dedup_by_section={dedup_by_section}"
        )

        if executor is not None:
            return self._retrieve_with_executor(
                query,
                top_k,
                dense_top_k,
                sparse_top_k,
                metadata_filter,
                executor,
                dedup_by_section,
            )
        else:
            return self._retrieve_serial(
                query,
                top_k,
                dense_top_k,
                sparse_top_k,
                metadata_filter,
                dedup_by_section,
            )

    # ── 有 executor：并发检索 + 可选循环扩大 ─────────────────────────

    def _retrieve_with_executor(
        self,
        query: str,
        top_k: int,
        dense_top_k: int,
        sparse_top_k: int,
        metadata_filter: dict[str, Any] | None,
        executor: ThreadPoolExecutor,
        dedup_by_section: bool,
    ) -> list[TextNode]:
        """并发检索路径。dedup_by_section=False 时不做循环扩大。"""

        max_mult = max(self.max_section_oversample_multiplier, 1)

        deduped: list[TextNode] = []
        multiplier = 1

        while multiplier <= max_mult:
            cur_dense_top_k = dense_top_k * multiplier
            cur_sparse_top_k = sparse_top_k * multiplier

            # ① 并发提交稠密 + 稀疏检索（dedup_by_section 透传）
            dense_future = executor.submit(
                self.dense_retriever.retrieve_with_score,
                query,
                cur_dense_top_k,
                dedup_by_section,
                metadata_filter,
            )
            sparse_future = executor.submit(
                self.sparse_retriever.retrieve_with_score,
                query,
                cur_sparse_top_k,
                dedup_by_section,
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

            # 如果都失败了，返回空
            if not dense_results and not sparse_results:
                self.logger.warning("[HybridRetriever] 所有检索都失败")
                return []

            # ② RRF 融合
            self.logger.info("[HybridRetriever] 执行 RRF 融合")
            if dedup_by_section:
                rrf_top_k = top_k * self.rrf_oversample_multiplier
            else:
                rrf_top_k = top_k
            fused_results = self.fuser.fuse_with_weights(
                results_list=[dense_results, sparse_results],
                weights=[self.dense_weight, self.sparse_weight],
                top_k=rrf_top_k,
            )

            # ③ 不要求 section 多样性 → 直接返回
            if not dedup_by_section:
                self.logger.info(
                    f"[HybridRetriever] 检索完成（dedup_by_section=False） | 返回 {len(fused_results)} 个结果"
                )
                return fused_results[:top_k]

            # ④ section 去重（处理跨检索器的 section 重复）
            deduped = self._dedup_by_section(fused_results, top_k)

            # ⑤ 够了就返回
            if len(deduped) >= top_k:
                self.logger.info(
                    f"[HybridRetriever] 检索完成 | 返回 {len(deduped)} 个不同 section"
                )
                return deduped[:top_k]

            # ⑥ 不够 → 扩大检索范围再试
            self.logger.info(
                f"[HybridRetriever] section 去重后仅 {len(deduped)} 个，"
                f"扩大检索 | multiplier={multiplier}"
            )
            multiplier += 1

        # 兜底：放大到最大倍数仍不够，诚实返回已收集的
        self.logger.info(
            f"[HybridRetriever] 达到最大放大倍数 | 返回 {len(deduped)} 个不同 section"
        )
        return deduped[:top_k]

    # ── 无 executor：串行检索（不循环扩大，但保持 RRF 过采样一致） ──

    def _retrieve_serial(
        self,
        query: str,
        top_k: int,
        dense_top_k: int,
        sparse_top_k: int,
        metadata_filter: dict[str, Any] | None,
        dedup_by_section: bool,
    ) -> list[TextNode]:
        """无注入 executor：串行执行（初始化等场景），不做循环扩大。"""
        dense_results: list = []
        sparse_results: list = []

        try:
            dense_results = self.dense_retriever.retrieve_with_score(
                query, dense_top_k, dedup_by_section, metadata_filter
            )
        except Exception as e:
            self.logger.error(f"[HybridRetriever] 稠密检索失败: {e}")
            dense_results = []

        try:
            sparse_results = self.sparse_retriever.retrieve_with_score(
                query, sparse_top_k, dedup_by_section, metadata_filter
            )
        except Exception as e:
            self.logger.error(f"[HybridRetriever] 稀疏检索失败: {e}")
            sparse_results = []

        if not dense_results and not sparse_results:
            self.logger.warning("[HybridRetriever] 所有检索都失败")
            return []

        self.logger.info("[HybridRetriever] 执行 RRF 融合")
        if dedup_by_section:
            rrf_top_k = top_k * self.rrf_oversample_multiplier
        else:
            rrf_top_k = top_k
        fused_results = self.fuser.fuse_with_weights(
            results_list=[dense_results, sparse_results],
            weights=[self.dense_weight, self.sparse_weight],
            top_k=rrf_top_k,
        )

        # dedup_by_section=False 时直接返回；True 时去重
        if not dedup_by_section:
            return fused_results[:top_k]
        return self._dedup_by_section(fused_results, top_k)

    # ── section 去重 ─────────────────────────────────────────────────

    @staticmethod
    def _dedup_by_section(nodes: list[TextNode], top_k: int) -> list[TextNode]:
        """按 (file_sha256, section_id) 去重，保留 RRF 排序靠前的 chunk。

        委托给 BaseRetriever.dedup_by_section 统一实现，避免逻辑分散。
        """
        scored = [(node, 0.0) for node in nodes]
        return [node for node, _ in BaseRetriever.dedup_by_section(scored, top_k)]
