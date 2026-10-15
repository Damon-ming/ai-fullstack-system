# app-server/src/com/damon/ming/ai/vector_db/chroma_store.py
import uuid
from pathlib import Path
from typing import Any

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.log import pin

DEFAULT_PERSIST_DIR = str(Path(__file__).resolve().parent.parent / "chroma_data")


class ChromaDBStore(BaseVectorStore):
    """
    ChromaDB 向量存储实现

    支持本地持久化和云端模式
    """

    def __init__(
        self,
        collection_name: str = "rag_collection",
        persist_directory: str = DEFAULT_PERSIST_DIR,
        host: str | None = None,
        port: int | None = None,
        embedding_dimension: int = 1024,
        **kwargs,
    ):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError("请安装 chromadb: pip install chromadb")

        self.logger = pin("ChromaDBStore")
        self.collection_name = collection_name
        self.embedding_dimension = embedding_dimension

        # 初始化客户端
        if host and port:
            # 远程模式
            self.client = chromadb.HttpClient(
                host=host, port=port, settings=Settings(anonymized_telemetry=False)
            )
            self.logger.info(f"[ChromaDBStore] 连接远程服务: {host}:{port}")
        else:
            # 本地持久化模式
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                # 关闭匿名遥测数据上报
                # 作用：禁止 ChromaDB 收集和发送匿名使用数据
                # 默认值：True（允许上报）
                settings=Settings(anonymized_telemetry=False),
            )
            self.logger.info(f"[ChromaDBStore] 初始化本地持久化: {persist_directory}")

        # 获取或创建 collection
        self.collection = self._get_or_create_collection()

        # 缓存节点（用于快速查询）
        # 考虑替换成redis
        self._node_cache = {}

    def _get_or_create_collection(self):
        """获取或创建 collection"""
        try:
            # 检查是否已存在
            existing = self.client.list_collections()
            if self.collection_name in [c.name for c in existing]:
                return self.client.get_collection(self.collection_name)
            else:
                # 创建新的 collection
                return self.client.create_collection(
                    name=self.collection_name, metadata={"hnsw:space": "cosine"}
                )
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 获取/创建 collection 失败: {e}")
            raise

    def add_documents(
        self, nodes: list[TextNode], batch_size: int = None, **kwargs
    ) -> list[str]:
        """添加文档到 ChromaDB"""
        if not nodes:
            return []

        ids = []
        documents = []
        embeddings = []
        metadatas = []

        for node in nodes:
            node_id = node.node_id or str(uuid.uuid4())
            if node.embedding and len(node.embedding) != self.embedding_dimension:
                self.logger.warning(
                    f"向量维度不匹配！配置期望={self.embedding_dimension}，"
                    f"当前文本向量长度={len(node.embedding)}，检查embedding模型"
                )
            ids.append(node_id)
            documents.append(node.text)
            embeddings.append(node.embedding)
            metadatas.append(node.metadata)

            # 缓存节点
            self._node_cache[node_id] = node

        try:
            self.collection.add(
                ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
            )
            self.logger.info(f"[ChromaDBStore] 添加 {len(nodes)} 个文档成功")
            return ids
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 添加文档失败: {e}")
            raise

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        """
        【本实现不内置embedding函数】
        请外部先将query文本转为向量，调用 similarity_search_by_vector
        """
        self.logger.warning(
            "ChromaDBStore.similarity_search 不支持文本直查，请使用similarity_search_by_vector"
        )
        return []

    def similarity_search_by_vector(
        self,
        query_vector: list[float],
        k: int = 4,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        """向量相似度检索"""
        try:
            # 构建 where 条件
            query_kwargs = {
                "query_embeddings": [query_vector],
                "n_results": k,
                "include": ["documents", "metadatas", "distances"],
            }
            if metadata_filter:
                query_kwargs["where"] = metadata_filter
            results = self.collection.query(**query_kwargs)

            if not results["ids"] or not results["ids"][0]:
                return []

            nodes = []
            # ChromaDB 默认使用 duckdb+parquet
            for i, node_id in enumerate(results["ids"][0]):
                node = TextNode(
                    id_=node_id,
                    text=results["documents"][0][i],
                    metadata=results["metadatas"][0][i],
                )
                # 添加距离分数
                node.metadata["_score"] = 1 - results["distances"][0][i]  # 转换为相似度
                nodes.append(node)

            self.logger.info(f"[ChromaDBStore] 检索到 {len(nodes)} 个结果")
            return nodes
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 向量检索失败: {e}")
            return []

    def delete(self, node_ids: list[str], **kwargs) -> bool:
        """删除文档"""
        try:
            self.collection.delete(ids=node_ids)
            for node_id in node_ids:
                self._node_cache.pop(node_id, None)
            self.logger.info(f"[ChromaDBStore] 删除 {len(node_ids)} 个文档成功")
            return True
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 删除失败: {e}")
            return False

    def get_by_id(self, node_id: str, **kwargs) -> TextNode | None:
        """根据 ID 获取文档"""
        # 先查缓存
        if node_id in self._node_cache:
            return self._node_cache[node_id]

        try:
            result = self.collection.get(ids=[node_id])
            if result["ids"]:
                node = TextNode(
                    id_=result["ids"][0],
                    text=result["documents"][0],
                    metadata=result["metadatas"][0],
                )
                self._node_cache[node_id] = node
                return node
            return None
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 获取文档失败: {e}")
            return None

    def get_by_metadata(
        self, metadata_filter: dict[str, Any], **kwargs
    ) -> list[TextNode]:
        """根据元数据查询"""
        try:
            results = self.collection.get(where=metadata_filter)
            if not results["ids"]:
                return []

            nodes = []
            for i, node_id in enumerate(results["ids"]):
                node = TextNode(
                    id_=node_id,
                    text=results["documents"][i],
                    metadata=results["metadatas"][i],
                )
                nodes.append(node)
                self._node_cache[node_id] = node

            return nodes
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 元数据查询失败: {e}")
            return []

    def count(self, **kwargs) -> int:
        """获取文档总数"""
        try:
            return self.collection.count()
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 获取总数失败: {e}")
            return 0

    def clear(self, **kwargs) -> bool:
        """清空所有文档"""
        try:
            # 删除 collection 并重建
            self.client.delete_collection(self.collection_name)
            self.collection = self._get_or_create_collection()
            self._node_cache.clear()
            self.logger.info("[ChromaDBStore] 清空成功")
            return True
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 清空失败: {e}")
            return False

    def get_collection_info(self) -> dict[str, Any]:
        """获取集合信息"""
        try:
            return {
                "provider": "chromadb",
                "collection_name": self.collection_name,
                "count": self.count(),
                "embedding_dimension": self.embedding_dimension,
            }
        except Exception as e:
            return {
                "provider": "chromadb",
                "collection_name": self.collection_name,
                "error": str(e),
            }
