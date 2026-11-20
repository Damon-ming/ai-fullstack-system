# app-server/src/com/damon/ming/ai/vector_db/chroma_store.py

from typing import Any

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.vector_db import register_engine
from src.com.damon.ming.ai.vector_db.base_vector_db import (
    VECTOR_SCORE_KEY,
    BaseVectorStore,
    ChromaParams,
    VectorStoreParams,
)
from src.com.damon.ming.log import pin
from src.com.damon.ming.utils.uuid import generate_uuid


@register_engine("chroma")
class ChromaDBStore(BaseVectorStore):
    """
    ChromaDB 向量存储实现

    支持本地持久化（PersistentClient）和远程模式（HttpClient）。
    参数通过 VectorStoreParams 注入，本实现不感知配置来源。
    """

    def __init__(self, params: VectorStoreParams):
        if not isinstance(params.engine_params, ChromaParams):
            raise TypeError("ChromaDBStore 需要 ChromaParams")
        super().__init__(params)
        self.chroma_params = params.engine_params
        self.logger = pin("ChromaDBStore")
        self._closed = False

        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError("请安装 chromadb: pip install chromadb")

        # 远程模式 vs 本地持久化
        if self.chroma_params.host and self.chroma_params.port:
            self.client = chromadb.HttpClient(
                host=self.chroma_params.host,
                port=self.chroma_params.port,
                settings=Settings(anonymized_telemetry=False),
            )
            self.logger.info(
                f"[ChromaDBStore] 远程模式: {self.chroma_params.host}:{self.chroma_params.port}"
            )
        else:
            self.client = chromadb.PersistentClient(
                path=self.chroma_params.persist_directory,
                settings=Settings(anonymized_telemetry=False),
            )
            self.logger.info(
                f"[ChromaDBStore] 本地持久化: {self.chroma_params.persist_directory}"
            )

        self.collection = self._get_or_create_collection()
        self.logger.info(
            f"[ChromaDBStore] 初始化完成: collection={self.params.shared_params.table_name}, "
            f"dim={self.params.shared_params.embedding_dimension}"
        )

    def _get_or_create_collection(self):
        """获取或创建 collection（幂等）"""
        try:
            existing = self.client.list_collections()
            collection_name = self.params.shared_params.table_name
            if collection_name in [c.name for c in existing]:
                return self.client.get_collection(collection_name)
            return self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 获取/创建 collection 失败: {e}")
            raise

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
        expected_dim = self.params.shared_params.embedding_dimension

        for node in nodes:
            node_id = node.node_id or generate_uuid()
            embedding = node.embedding
            actual_dim = len(embedding) if embedding is not None else 0
            if actual_dim != expected_dim:
                raise ValueError(
                    f"向量维度不匹配: 期望 {expected_dim}, "
                    f"实际 {actual_dim}, node_id={node_id}"
                )
            ids.append(node_id)
            documents.append(node.text)
            embeddings.append(embedding)
            metadatas.append(node.metadata)

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

    def similarity_search_by_vector(
        self,
        query_vector: list[float],
        k: int,
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

            result_ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0]
            nodes = []
            for node_id, document, metadata, distance in zip(
                result_ids, documents, metadatas, distances
            ):
                node = TextNode(
                    id_=node_id,
                    text=document,
                    metadata=metadata,
                )
                node.metadata[VECTOR_SCORE_KEY] = 1 - distance
                nodes.append(node)

            return nodes
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 向量检索失败: {e}")
            return []

    def delete_by_metadata(self, metadata_filter: dict[str, Any], **kwargs) -> int:
        """按元数据查询并删除匹配文档，返回删除数量。

        查询失败抛 RuntimeError；缺少有效过滤条件时抛 ValueError。
        """
        if not metadata_filter:
            raise ValueError("删除操作必须提供有效的 metadata_filter")

        try:
            results = self.collection.get(where=metadata_filter)
            if not results["ids"]:
                return 0
            node_ids = results["ids"]
            self.collection.delete(ids=node_ids)
            return len(node_ids)
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 按元数据删除失败: {e}")
            raise RuntimeError(f"向量库删除失败: {e}") from e

    def get_by_metadata(
        self, metadata_filter: dict[str, Any], **kwargs
    ) -> list[TextNode]:
        """按元数据查询。不缓存：调用方（ingest 去重、constructor）可能修改返回节点。"""
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
        不缓存：返回的节分片后续会被 constructor 合并修改，缓存会导致过期数据。
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
            return nodes
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 批量元数据查询失败: {e}")
            return []

    def get_distinct_metadata_values(self, key: str) -> set[str] | None:
        """返回 collection 中指定 metadata 字段的非空字符串值。"""
        try:
            results = self.collection.get(include=["metadatas"])
            return {
                metadata[key]
                for metadata in results.get("metadatas", [])
                if metadata and isinstance(metadata.get(key), str) and metadata[key]
            }
        except Exception as e:
            self.logger.error(
                f"[ChromaDBStore] 查询 metadata distinct 值失败 | key={key}: {e}"
            )
            return None

    def update_metadata_by_filter(
        self,
        metadata_filter: dict[str, Any],
        updates: dict[str, Any] | None = None,
        remove_keys: set[str] | None = None,
    ) -> int:
        """通用 metadata 更新，支持按 metadata 条件更新或移除字段。"""
        try:
            results = self.collection.get(
                where=metadata_filter,
                include=["metadatas"],
            )
            ids = results.get("ids", [])
            metadatas = results.get("metadatas", [])
            if not ids:
                return 0

            updated_metadatas = []
            for metadata in metadatas:
                updated = dict(metadata or {})
                for key in remove_keys or set():
                    updated.pop(key, None)
                updated.update(updates or {})
                updated_metadatas.append(updated)

            self.collection.update(ids=ids, metadatas=updated_metadatas)
            return len(ids)
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 更新 metadata 失败: {e}")
            raise RuntimeError(f"向量库 metadata 更新失败: {e}") from e

    def count(self, **kwargs) -> int:
        try:
            return self.collection.count()
        except Exception as e:
            self.logger.error(f"[ChromaDBStore] 获取总数失败: {e}")
            return 0

    # ── 生命周期 ────────────────────────────────────────────────────

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.logger.info("[ChromaDBStore] 资源已释放")
