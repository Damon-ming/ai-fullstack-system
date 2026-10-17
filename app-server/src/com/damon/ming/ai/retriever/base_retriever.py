# app-server/src/com/damon/ming/ai/retriever/base_retriever.py
from abc import ABC, abstractmethod
from typing import Any

from llama_index.core.schema import TextNode


def _extract_section_key(node: TextNode) -> tuple[str, str] | None:
    """提取节点的 section 去重键。

    Returns:
        (file_sha256, section_id) 元组，元数据缺失时返回 None。
    """
    file_sha256 = node.metadata.get("file_sha256", "")
    section_id = node.metadata.get("section_id", "")
    if not file_sha256 or not section_id:
        return None
    return (file_sha256, section_id)


class BaseRetriever(ABC):
    """检索器抽象基类"""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int,
        dedup_by_section: bool,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[TextNode]:
        pass

    @abstractmethod
    def retrieve_with_score(
        self,
        query: str,
        top_k: int,
        dedup_by_section: bool,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[tuple[TextNode, float]]:
        pass

    @staticmethod
    def dedup_by_section(
        scored_nodes: list[tuple[TextNode, float]],
        top_k: int,
    ) -> list[tuple[TextNode, float]]:
        """按 (file_sha256, section_id) 去重，保留排序靠前的 chunk。

        保证输出中每个 section 只出现一次，最大化 section 多样性。
        返回数量 <= top_k（取决于输入中有多少不同 section）。
        没有 section 元数据的 chunk 会被跳过（不进入结果）。
        """
        seen: set[tuple[str, str]] = set()
        result: list[tuple[TextNode, float]] = []
        for node, score in scored_nodes:
            key = _extract_section_key(node)
            if key is None:
                continue
            if key in seen:
                continue
            seen.add(key)
            result.append((node, score))
            if len(result) >= top_k:
                break
        return result


class DenseRetriever(BaseRetriever):
    """稠密检索（向量）"""

    def __init__(self, vector_store, embedding_service):
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    def retrieve(
        self,
        query: str,
        top_k: int,
        dedup_by_section: bool,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[TextNode]:
        scored_nodes = self.retrieve_with_score(
            query, top_k, dedup_by_section, metadata_filter
        )
        return [node for node, _ in scored_nodes]

    def retrieve_with_score(
        self,
        query: str,
        top_k: int,
        dedup_by_section: bool,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[tuple[TextNode, float]]:
        # 1. 生成查询向量
        query_vector = self.embedding_service.embed_query(query)

        # 2. 向量检索，透传 filter 到向量库
        nodes = self.vector_store.similarity_search_by_vector(
            query_vector=query_vector, k=top_k, metadata_filter=metadata_filter
        )
        scored = [(node, node.metadata.get("_score", 0.0)) for node in nodes]

        # 3. 可选的 section 去重
        if dedup_by_section:
            return self.dedup_by_section(scored, top_k)
        return scored


class SparseRetriever(BaseRetriever):
    """稀疏检索（BM25/关键词）"""

    def __init__(self, bm25_index):
        self.bm25_index = bm25_index

    def retrieve(
        self,
        query: str,
        top_k: int,
        dedup_by_section: bool,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[TextNode]:
        scored_nodes = self.retrieve_with_score(
            query, top_k, dedup_by_section, metadata_filter
        )
        return [node for node, _ in scored_nodes]

    def retrieve_with_score(
        self,
        query: str,
        top_k: int,
        dedup_by_section: bool,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[tuple[TextNode, float]]:
        # P2 修复：top_k <= 0 时 argsort[-0:] 会返回整个语料库
        if top_k < 1:
            return []

        scores = self.bm25_index.get_scores(query)
        top_indices = scores.argsort()[-top_k:][::-1]
        candidates = [
            (self.bm25_index.corpus[i], float(scores[i])) for i in top_indices
        ]

        # 元数据过滤：BM25 内存索引只能检索后过滤
        if metadata_filter:
            filtered = []
            for node, score in candidates:
                match = True
                for k, v in metadata_filter.items():
                    if node.metadata.get(k) != v:
                        match = False
                        break
                if match:
                    filtered.append((node, score))
            candidates = filtered

        # 可选的 section 去重
        if dedup_by_section:
            return self.dedup_by_section(candidates, top_k)
        return candidates
