# app-server/src/com/damon/ming/ai/retriever/rrf.py

from llama_index.core.schema import TextNode
from src.com.damon.ming.log import pin


class ReciprocalRankFusion:
    """
    RRF (Reciprocal Rank Fusion) 融合排序

    公式: score = Σ 1 / (k + rank)
    其中 k 是常数（通常为 60）

    注意：所有参数无默认值，调用方必须显式传入。
    """

    def __init__(self, k: int):
        """
        Args:
            k: RRF 常数。必须显式传入，无默认值。
        """
        self.k = k
        self.logger = pin("RRF")

    def fuse(
        self, results_list: list[list[tuple[TextNode, float]]], top_k: int
    ) -> list[TextNode]:
        """
        融合多个检索结果

        Args:
            results_list: 多个检索器的结果列表 [[(node, score), ...], ...]
            top_k: 最终返回数量。必须显式传入，无默认值。

        Returns:
            list[TextNode]: 融合排序后的结果
        """
        if not results_list:
            return []

        # 收集所有节点并计算 RRF 分数
        node_scores: dict[str, float] = {}
        node_map: dict[str, TextNode] = {}

        for _, results in enumerate(results_list):
            for rank, (node, _) in enumerate(results, start=1):
                # todo 但是存在致命隐患,后期改
                node_id = node.node_id or id(node)

                # RRF 分数 = 1 / (k + rank)
                rrf_score = 1.0 / (self.k + rank)

                if node_id in node_scores:
                    node_scores[node_id] += rrf_score
                else:
                    node_scores[node_id] = rrf_score
                    node_map[node_id] = node

        # 按 RRF 分数排序
        sorted_nodes = sorted(
            node_map.items(), key=lambda x: node_scores.get(x[0], 0), reverse=True
        )

        # 返回 Top-K
        result_nodes = []
        for node_id, _ in sorted_nodes[:top_k]:
            node = node_map[node_id]
            # 附加融合分数
            node.metadata["_rrf_score"] = node_scores[node_id]
            result_nodes.append(node)

        self.logger.info(
            f"[RRF] 融合完成 | 输入 {len(results_list)} 个结果集 | 输出 {len(result_nodes)} 个节点"
        )
        return result_nodes

    def fuse_with_weights(
        self,
        results_list: list[list[tuple[TextNode, float]]],
        weights: list[float],
        top_k: int,
    ) -> list[TextNode]:
        """
        带权重的 RRF 融合

        Args:
            results_list: 多个检索器的结果列表
            weights: 每个检索器的权重（如 [0.7, 0.3]）
            top_k: 最终返回数量。必须显式传入，无默认值。
        """
        if len(results_list) != len(weights):
            raise ValueError("results_list 和 weights 长度必须相同")

        node_scores: dict[str, float] = {}
        node_map: dict[str, TextNode] = {}

        for rank_idx, results in enumerate(results_list):
            weight = weights[rank_idx]
            for rank, (node, _) in enumerate(results, start=1):
                node_id = node.node_id or id(node)
                rrf_score = weight * (1.0 / (self.k + rank))

                if node_id in node_scores:
                    node_scores[node_id] += rrf_score
                else:
                    node_scores[node_id] = rrf_score
                    node_map[node_id] = node

        sorted_nodes = sorted(
            node_map.items(), key=lambda x: node_scores.get(x[0], 0), reverse=True
        )

        result_nodes = []
        for node_id, _ in sorted_nodes[:top_k]:
            node = node_map[node_id]
            node.metadata["_rrf_score"] = node_scores[node_id]
            result_nodes.append(node)

        return result_nodes
