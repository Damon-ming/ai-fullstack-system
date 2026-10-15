# app-server/src/com/damon/ming/ai/retriever/base_retriver.py
from abc import ABC, abstractmethod
from typing import Any

from llama_index.core.schema import TextNode


class BaseRetriever(ABC):
    """检索器抽象基类"""

    @abstractmethod
    def retrieve(
        self, query: str, top_k: int = 10, metadata_filter: dict[str, Any] | None = None
    ) -> list[TextNode]:
        pass

    @abstractmethod
    def retrieve_with_score(
        self, query: str, top_k: int = 10, metadata_filter: dict[str, Any] | None = None
    ) -> list[tuple[TextNode, float]]:
        pass


class DenseRetriever(BaseRetriever):
    """稠密检索（向量）"""

    def __init__(self, vector_store, embedding_service):
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    def retrieve(
        self, query: str, top_k: int = 50, metadata_filter: dict[str, Any] | None = None
    ) -> list[TextNode]:
        scored_nodes = self.retrieve_with_score(query, top_k, metadata_filter)
        return [node for node, _ in scored_nodes]

    def retrieve_with_score(
        self, query: str, top_k: int = 50, metadata_filter: dict[str, Any] | None = None
    ) -> list[tuple[TextNode, float]]:
        # 1. 生成查询向量
        query_vector = self.embedding_service.embed_query(query)

        # 2. 向量检索，透传filter到向量库
        nodes = self.vector_store.similarity_search_by_vector(
            query_vector=query_vector, k=top_k, metadata_filter=metadata_filter
        )
        # 提取分数
        return [(node, node.metadata.get("_score", 0.0)) for node in nodes]


class SparseRetriever(BaseRetriever):
    """稀疏检索（BM25/关键词）"""

    def __init__(self, bm25_index):
        self.bm25_index = bm25_index

    def retrieve(
        self, query: str, top_k: int = 50, metadata_filter: dict[str, Any] | None = None
    ) -> list[TextNode]:
        scored_nodes = self.retrieve_with_score(query, top_k, metadata_filter)
        return [node for node, _ in scored_nodes]

    def retrieve_with_score(
        self, query: str, top_k: int = 50, metadata_filter: dict[str, Any] | None = None
    ) -> list[tuple[TextNode, float]]:
        scores = self.bm25_index.get_scores(query)
        top_indices = scores.argsort()[-top_k:][::-1]
        candidates = [
            (self.bm25_index.corpus[i], float(scores[i])) for i in top_indices
        ]

        # 元数据过滤：BM25内存索引只能检索后过滤
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

        return candidates
