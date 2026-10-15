# app-server/src/com/damon/ming/ai/vector_db/base_vector_db.py

from abc import ABC, abstractmethod
from typing import Any

from llama_index.core.schema import TextNode


class BaseVectorStore(ABC):
    """
    向量存储抽象基类

    定义统一的向量存储接口，支持多种向量数据库：
    - ChromaDB (本地/云端)
    - PGVector (PostgreSQL)
    - Milvus (本地/分布式)
    - Pinecone (云端)
    - FAISS (本地内存)
    """

    @abstractmethod
    def add_documents(self, nodes: list[TextNode], **kwargs) -> list[str]:
        """
        添加文档到向量库

        Args:
            nodes: TextNode 列表 (包含文本、元数据、向量)
            **kwargs: 各实现特有参数

        Returns:
            List[str]: 添加成功的节点 ID 列表
        """

    @abstractmethod
    def similarity_search(
        self,
        query: str,
        k: int = 4,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        """
        向量相似度检索

        Args:
            query: 查询文本
            k: 返回 Top-K 结果
            metadata_filter: 元数据过滤条件
            **kwargs: 各实现特有参数

        Returns:
            List[TextNode]: 检索结果列表（包含文本和元数据）
        """

    @abstractmethod
    def similarity_search_by_vector(
        self,
        query_vector: list[float],
        k: int = 4,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        """
        向量相似度检索（直接传入向量）

        Args:
            query_vector: 查询向量
            k: 返回 Top-K 结果
            metadata_filter: 元数据过滤条件
            **kwargs: 各实现特有参数

        Returns:
            List[TextNode]: 检索结果列表
        """

    @abstractmethod
    def delete(self, node_ids: list[str], **kwargs) -> bool:
        """
        删除文档

        Args:
            node_ids: 要删除的节点 ID 列表
            **kwargs: 各实现特有参数

        Returns:
            bool: 是否删除成功
        """

    @abstractmethod
    def get_by_id(self, node_id: str, **kwargs) -> TextNode | None:
        """
        根据 ID 获取文档

        Args:
            node_id: 节点 ID
            **kwargs: 各实现特有参数

        Returns:
            Optional[TextNode]: 对应的节点，不存在返回 None
        """

    @abstractmethod
    def get_by_metadata(
        self, metadata_filter: dict[str, Any], **kwargs
    ) -> list[TextNode]:
        """
        根据元数据批量查询

        Args:
            metadata_filter: 元数据过滤条件
            **kwargs: 各实现特有参数

        Returns:
            List[TextNode]: 匹配的节点列表
        """

    @abstractmethod
    def count(self, **kwargs) -> int:
        """
        获取文档总数

        Returns:
            int: 文档总数
        """

    @abstractmethod
    def clear(self, **kwargs) -> bool:
        """
        清空所有文档

        Returns:
            bool: 是否清空成功
        """

    @abstractmethod
    def get_collection_info(self) -> dict[str, Any]:
        """
        获取集合/索引信息（用于监控和调试）

        Returns:
            Dict: 包含集合名称、维度、文档数等信息
        """
