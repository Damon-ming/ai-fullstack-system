# app-server/src/com/damon/ming/ai/vector_db/chroma_store.py

import threading
import uuid
from collections import OrderedDict
from typing import Any

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.vector_db import register_engine
from src.com.damon.ming.ai.vector_db.base_vector_db import (
    BaseVectorStore,
    VectorStoreParams,
)
from src.com.damon.ming.log import pin


@register_engine("chroma")
class ChromaDBStore(BaseVectorStore):
    """
    ChromaDB 向量存储实现

    支持本地持久化（PersistentClient）和远程模式（HttpClient）。
    参数通过 VectorStoreParams 注入，本实现不感知配置来源。
    """

    def __init__(self, params: VectorStoreParams):
        super().__init__(params)
        self.logger = pin("ChromaDBStore")
        self._closed = False
        self._node_cache: OrderedDict[str, TextNode] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._CACHE_MAX = params.extra.get("cache_max", 5000)  # LRU 上限（YAML 可配）

        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError("请安装 chromadb: pip install chromadb")

        # 远程模式 vs 本地持久化
        if self.params.host and self.params.port:
            self.client = chromadb.HttpClient(
                host=self.params.host,
                port=self.params.port,
                settings=Settings(anonymized_telemetry=False),
            )
            self.logger.info(
                f"[ChromaDBStore] 远程模式: {self.params.host}:{self.params.port}"
            )
        else:
            self.client = chromadb.PersistentClient(
                path=self.params.persist_directory,
                settings=Settings(anonymized_telemetry=False),
            )
            self.logger.info(
                f"[ChromaDBStore] 本地持久化: {self.params.persist_directory}"
            )

        self.collection = self._get_or_create_collection()
        self.logger.info(
            f"[ChromaDBStore] 初始化完成: collection={self.params.collection_name}, "
            f"dim={self.params.embedding_dimension}"
        )

    def _get_or_create_collection(self):
        """获取或创建 collection（幂等）"""
        try:
            existing = self.client.list_collections()
            if self.params.collection_name in [c.name for c in existing]:
                return self.client.get_collection(self.params.collection_name)
            return self.client.create_collection(
                name=self.params.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 获取/创建 collection 失败: {e}")
            raise

    # ── LRU 缓存辅助 ───────────────────────────────────────────────

    def _cache_put(self, node_id: str, node: TextNode) -> None:
        """写入缓存 + LRU 淘汰（超上限时移除最久未用条目）。"""
        self._node_cache[node_id] = node
        self._node_cache.move_to_end(node_id)
        if len(self._node_cache) > self._CACHE_MAX:
            self._node_cache.popitem(last=False)

    def _cache_get(self, node_id: str) -> TextNode | None:
        """读取缓存并更新 LRU 顺序。"""
        node = self._node_cache.get(node_id)
        if node is not None:
            self._node_cache.move_to_end(node_id)
        return node

    # ── 核心 CRUD ──────────────────────────────────────────────────

    def add_documents(
        self, nodes: list[TextNode], batch_size: int | None = None, **kwargs
    ) -> list[str]:
        if not nodes:
            return []

        ids = []
        documents = []
        embeddings = []
        metadatas = []

        for node in nodes:
            node_id = node.node_id or str(uuid.uuid4())
            if (
                node.embedding
                and len(node.embedding) != self.params.embedding_dimension
            ):
                self.logger.warning(
                    f"向量维度不匹配！期望={self.params.embedding_dimension}，"
                    f"实际={len(node.embedding)}，node_id={node_id}"
                )
            ids.append(node_id)
            documents.append(node.text)
            embeddings.append(node.embedding)
            metadatas.append(node.metadata)

        with self._cache_lock:
            for node, node_id in zip(nodes, ids):
                self._cache_put(node_id, node)

        try:
            self.collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
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
        self.logger.warning(
            "[ChromaDBStore] similarity_search 不支持文本直查，请使用 similarity_search_by_vector"
        )
        return []

    def similarity_search_by_vector(
        self,
        query_vector: list[float],
        k: int = 4,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        try:
            query_kwargs: dict[str, Any] = {
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
            for i, node_id in enumerate(results["ids"][0]):
                node = TextNode(
                    id_=node_id,
                    text=results["documents"][0][i],
                    metadata=results["metadatas"][0][i],
                )
                node.metadata["_score"] = 1 - results["distances"][0][i]
                nodes.append(node)

            return nodes
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 向量检索失败: {e}")
            return []

    def delete(self, node_ids: list[str], **kwargs) -> bool:
        try:
            self.collection.delete(ids=node_ids)
            with self._cache_lock:
                for node_id in node_ids:
                    self._node_cache.pop(node_id, None)
            return True
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 删除失败: {e}")
            return False

    def get_by_id(self, node_id: str, **kwargs) -> TextNode | None:
        with self._cache_lock:
            cached = self._cache_get(node_id)
        if cached is not None:
            return cached
        try:
            result = self.collection.get(ids=[node_id])
            if result["ids"]:
                node = TextNode(
                    id_=result["ids"][0],
                    text=result["documents"][0],
                    metadata=result["metadatas"][0],
                )
                with self._cache_lock:
                    self._cache_put(node_id, node)
                return node
            return None
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 获取文档失败: {e}")
            return None

    def get_by_metadata(
        self, metadata_filter: dict[str, Any], **kwargs
    ) -> list[TextNode]:
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
            with self._cache_lock:
                for node in nodes:
                    self._cache_put(node.node_id, node)
            return nodes
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 元数据查询失败: {e}")
            return []

    def get_by_metadata_batch(
        self,
        filters: list[dict[str, Any]],
        **kwargs,
    ) -> list[TextNode]:
        """批量元数据查询：$or 合并多个 filter，单次 collection.get。

        将 N 个独立查询合并为 1 次 SQLite 扫描，SectionReconstructor 场景下
        显著减少 ChromaDB 查询耗时。
        """
        if not filters:
            return []
        # 单条件直接走原接口，避免 $or 开销
        if len(filters) == 1:
            return self.get_by_metadata(filters[0])
        try:
            results = self.collection.get(where={"$or": filters})
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
            with self._cache_lock:
                for node in nodes:
                    self._cache_put(node.node_id, node)
            return nodes
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 批量元数据查询失败: {e}")
            return []

    def count(self, **kwargs) -> int:
        try:
            return self.collection.count()
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 获取总数失败: {e}")
            return 0

    def clear(self, **kwargs) -> bool:
        try:
            with self._cache_lock:
                self.client.delete_collection(self.params.collection_name)
                self.collection = self._get_or_create_collection()
                self._node_cache.clear()
            return True
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 清空失败: {e}")
            return False

    def get_collection_info(self) -> dict[str, Any]:
        try:
            return {
                "provider": "chromadb",
                "collection_name": self.params.collection_name,
                "count": self.count(),
                "embedding_dimension": self.params.embedding_dimension,
            }
        except Exception as e:
            return {
                "provider": "chromadb",
                "collection_name": self.params.collection_name,
                "error": str(e),
            }

    # ── 生命周期 ────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            self.client.heartbeat()
            return True
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 健康检查失败: {e}")
            return False

    def close(self) -> None:
        with self._cache_lock:
            if self._closed:
                return
            self._closed = True
            self._node_cache.clear()
        self.logger.info("[ChromaDBStore] 资源已释放")
