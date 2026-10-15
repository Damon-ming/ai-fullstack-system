# app-server/src/com/damon/ming/ai/vector_db/pgvector_store.py
import json
import uuid
from typing import TYPE_CHECKING, Any

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.log import pin

if TYPE_CHECKING:
    from src.com.damon.ming.db import DbConnection


class PGVectorStore(BaseVectorStore):
    """
    PGVector (PostgreSQL + pgvector) 向量存储实现。

    通过共享的 DbConnection（SQLAlchemy 连接池）操作数据库，
    复用连接池、重试、健康检查等能力。

    需要 PostgreSQL 12+ 且安装 pgvector 扩展。
    """

    def __init__(
        self,
        db_connection: "DbConnection",
        table_name: str = "documents",
        embedding_dimension: int = 768,
        **kwargs,
    ):
        self.logger = pin("PGVectorStore")
        self.db = db_connection
        self.table_name = table_name
        self.embedding_dimension = embedding_dimension
        self._init_table()

    def _init_table(self):
        """初始化表结构和索引"""
        try:
            # 启用 pgvector 扩展
            self.db.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # 创建表
            self.db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id VARCHAR(64) PRIMARY KEY,
                    text TEXT NOT NULL,
                    embedding VECTOR({self.embedding_dimension}),
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )

            # 创建 HNSW 索引（加速检索）
            self.db.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_embedding
                ON {self.table_name}
                USING hnsw (embedding vector_cosine_ops);
                """
            )

            self.logger.info(f"[PGVectorStore] 表初始化成功: {self.table_name}")
        except Exception as e:
            self.logger.error(f"[PGVectorStore] 初始化失败: {e}")
            raise

    def add_documents(self, nodes: list[TextNode], **kwargs) -> list[str]:
        """添加文档到 PGVector"""
        if not nodes:
            return []

        ids = []
        for node in nodes:
            node_id = node.node_id or str(uuid.uuid4())
            ids.append(node_id)

            # 将向量转为 PostgreSQL vector 格式
            embedding_str = f"[{','.join(str(x) for x in node.embedding)}]"

            self.db.execute(
                f"""
                INSERT INTO {self.table_name}
                (id, text, embedding, metadata)
                VALUES (%s, %s, CAST(%s AS vector), %s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    text = EXCLUDED.text,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
                """,
                (node_id, node.text, embedding_str, json.dumps(node.metadata)),
            )

        self.logger.info(f"[PGVectorStore] 添加 {len(nodes)} 个文档成功")
        return ids

    def similarity_search_by_vector(
        self,
        query_vector: list[float],
        k: int = 4,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        """向量相似度检索"""
        try:
            embedding_str = f"[{','.join(str(x) for x in query_vector)}]"

            if metadata_filter:
                # 使用 JSONB 包含操作符 @>，参数化避免 SQL 注入
                rows = self.db.execute(
                    f"""
                    SELECT id, text, metadata,
                           1 - (embedding <=> CAST(%s AS vector)) AS similarity
                    FROM {self.table_name}
                    WHERE metadata @> %s::jsonb
                    ORDER BY embedding <=> CAST(%s AS vector)
                    LIMIT %s
                    """,
                    (embedding_str, json.dumps(metadata_filter), embedding_str, k),
                    commit=False,
                    fetch=True,
                )
            else:
                rows = self.db.execute(
                    f"""
                    SELECT id, text, metadata,
                           1 - (embedding <=> CAST(%s AS vector)) AS similarity
                    FROM {self.table_name}
                    ORDER BY embedding <=> CAST(%s AS vector)
                    LIMIT %s
                    """,
                    (embedding_str, embedding_str, k),
                    commit=False,
                    fetch=True,
                )

            nodes = []
            if rows:
                for row in rows:
                    node = TextNode(id_=row[0], text=row[1], metadata=row[2])
                    node.metadata["_score"] = row[3]
                    nodes.append(node)

            self.logger.info(f"[PGVectorStore] 检索到 {len(nodes)} 个结果")
            return nodes
        except Exception as e:
            self.logger.error(f"[PGVectorStore] 检索失败: {e}")
            return []

    def similarity_search(self, query: str, k: int = 4, **kwargs) -> list[TextNode]:
        """PGVector 不支持文本直接查询，需要使用向量"""
        raise NotImplementedError(
            "PGVector 需要向量查询，请使用 similarity_search_by_vector"
        )

    def delete(self, node_ids: list[str], **kwargs) -> bool:
        """删除文档"""
        try:
            placeholders = ",".join(["%s"] * len(node_ids))
            self.db.execute(
                f"DELETE FROM {self.table_name} WHERE id IN ({placeholders})",
                tuple(node_ids),
            )
            self.logger.info(f"[PGVectorStore] 删除 {len(node_ids)} 个文档成功")
            return True
        except Exception as e:
            self.logger.error(f"[PGVectorStore] 删除失败: {e}")
            return False

    def get_by_id(self, node_id: str, **kwargs) -> TextNode | None:
        """根据 ID 获取文档"""
        try:
            rows = self.db.execute(
                f"SELECT id, text, metadata FROM {self.table_name} WHERE id = %s",
                (node_id,),
                commit=False,
                fetch=True,
            )
            if rows:
                row = rows[0]
                return TextNode(id_=row[0], text=row[1], metadata=row[2])
            return None
        except Exception as e:
            self.logger.error(f"[PGVectorStore] 获取文档失败: {e}")
            return None

    def get_by_metadata(
        self, metadata_filter: dict[str, Any], **kwargs
    ) -> list[TextNode]:
        """根据元数据查询"""
        try:
            rows = self.db.execute(
                f"SELECT id, text, metadata FROM {self.table_name} WHERE metadata @> %s::jsonb",
                (json.dumps(metadata_filter),),
                commit=False,
                fetch=True,
            )
            nodes = []
            if rows:
                for row in rows:
                    nodes.append(TextNode(id_=row[0], text=row[1], metadata=row[2]))
            return nodes
        except Exception as e:
            self.logger.error(f"[PGVectorStore] 元数据查询失败: {e}")
            return []

    def count(self, **kwargs) -> int:
        """获取文档总数"""
        try:
            rows = self.db.execute(
                f"SELECT COUNT(*) FROM {self.table_name}",
                commit=False,
                fetch=True,
            )
            return rows[0][0] if rows else 0
        except Exception as e:
            self.logger.error(f"[PGVectorStore] 获取总数失败: {e}")
            return 0

    def clear(self, **kwargs) -> bool:
        """清空所有文档"""
        try:
            self.db.execute(f"DELETE FROM {self.table_name}")
            self.logger.info("[PGVectorStore] 清空成功")
            return True
        except Exception as e:
            self.logger.error(f"[PGVectorStore] 清空失败: {e}")
            return False

    def get_collection_info(self) -> dict[str, Any]:
        """获取集合信息"""
        try:
            return {
                "provider": "pgvector",
                "table_name": self.table_name,
                "count": self.count(),
                "embedding_dimension": self.embedding_dimension,
            }
        except Exception as e:
            return {
                "provider": "pgvector",
                "table_name": self.table_name,
                "error": str(e),
            }

    def close(self):
        """关闭底层数据库连接池。"""
        self.db.close()
