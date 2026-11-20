# app-server/src/com/damon/ming/ai/vector_db/pgvector_store.py
"""
PGVector 向量存储实现 —— PostgreSQL + pgvector 扩展。

使用 SQLAlchemy 同步引擎（与项目 db 模块一致），通过 text() 执行原生 SQL
调用 pgvector 特有操作符（<=>、::vector 等）。

设计对齐 ChromaDBStore：
  - 异常行为规范与 base_vector_db.py 一致
  - 参数通过 VectorStoreParams 注入，不感知配置来源

建表 DDL（首次初始化自动执行）：
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE TABLE IF NOT EXISTS <table_name> (
      id          TEXT PRIMARY KEY,
      document    TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding   vector(<dim>) NOT NULL
  );
  CREATE INDEX IF NOT EXISTS <table_name>_embedding_idx
    ON <table_name> USING hnsw (embedding vector_cosine_ops)
    WITH (m = <hnsw_m>, ef_construction = <hnsw_ef_construction>);
  CREATE INDEX IF NOT EXISTS <table_name>_metadata_idx
    ON <table_name> USING gin (metadata);
"""

import json
import re
from typing import Any

from llama_index.core.schema import TextNode
from sqlalchemy import column, literal, table, text, update
from sqlalchemy.dialects.postgresql import JSONB
from src.com.damon.ming.ai.vector_db import register_engine
from src.com.damon.ming.ai.vector_db.base_vector_db import (
    BaseVectorStore,
    PGVectorParams,
    VectorStoreParams,
)
from src.com.damon.ming.log import pin
from src.com.damon.ming.utils.uuid import generate_uuid

# 标识符白名单：仅允许字母、数字、下划线，防止 SQL 注入
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_]\w*$", re.ASCII)

# SQL 常量：去重 + 避免 Sonar S1192（重复字面符）
_SQL_AND = " AND "
_SQL_OR = " OR "


def _sanitize_identifier(name: str, context: str) -> str:
    """校验 SQL 标识符（表名/字段名），仅允许 [a-zA-Z_][a-zA-Z0-9_]*。"""
    if not _IDENTIFIER_PATTERN.match(name):
        raise ValueError(
            f"非法 {context}: '{name}'。仅允许字母、数字、下划线，且不能以数字开头。"
        )
    return name


@register_engine("pgvector")
class PGVectorStore(BaseVectorStore):
    """PostgreSQL + pgvector 向量存储实现。"""

    def __init__(self, params: VectorStoreParams):
        if not isinstance(params.engine_params, PGVectorParams):
            raise TypeError("PGVectorStore 需要 PGVectorParams")
        super().__init__(params)
        self.pgvector_params = params.engine_params
        self.logger = pin("PGVectorStore")
        self._closed = False

        self._table_name = _sanitize_identifier(
            params.shared_params.table_name, "table_name"
        )
        self._engine = self._create_engine()
        self._ensure_schema()
        self.logger.info(
            "[PGVectorStore] 初始化完成: table=%s, dim=%d",
            self._table_name,
            params.shared_params.embedding_dimension,
        )

    # ── 引擎 & 建表 ───────────────────────────────────────────────

    def _create_engine(self):
        """创建 SQLAlchemy 引擎。"""
        try:
            from sqlalchemy import create_engine, text
        except ImportError:
            raise ImportError("请安装 sqlalchemy: pip install sqlalchemy>=2.0.0")

        url = self.pgvector_params.connection_string
        if not url:
            raise ValueError(
                "PGVectorStore 需要 connection_string，请在 YAML 中配置 DB_URL"
            )

        min_conn = self.pgvector_params.pool_min_conn
        max_conn = self.pgvector_params.pool_max_conn
        if max_conn < min_conn:
            raise ValueError(
                f"pool_max_conn({max_conn}) 不能小于 pool_min_conn({min_conn})"
            )

        engine = create_engine(
            url,
            pool_size=min_conn,
            max_overflow=max_conn - min_conn,
            pool_recycle=self.pgvector_params.pool_recycle,
        )

        # 测试连接
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()

        return engine

    def _ensure_schema(self):
        """确保 pgvector 扩展、表、索引存在。"""

        dim = self.params.shared_params.embedding_dimension
        table = self._table_name
        m = self.pgvector_params.hnsw_m
        ef = self.pgvector_params.hnsw_ef_construction

        # 参数范围校验
        if not (1 <= dim <= 16000):
            raise ValueError(f"embedding_dimension 超出合理范围: {dim}")
        if not (1 <= m <= 100):
            raise ValueError(f"hnsw_m 超出合理范围: {m}")
        if not (1 <= ef <= 1000):
            raise ValueError(f"hnsw_ef_construction 超出合理范围: {ef}")

        ddl_statements = [
            "CREATE EXTENSION IF NOT EXISTS vector",
            (
                f"CREATE TABLE IF NOT EXISTS {table} ("
                "  id        TEXT PRIMARY KEY,"
                "  document  TEXT NOT NULL,"
                "  metadata  JSONB NOT NULL DEFAULT '{}'::jsonb,"
                f"  embedding vector({dim}) NOT NULL"
                ")"
            ),
            (
                f"CREATE INDEX IF NOT EXISTS {table}_embedding_idx"
                f"  ON {table} USING hnsw (embedding vector_cosine_ops)"
                f"  WITH (m = {m}, ef_construction = {ef})"
            ),
            (
                f"CREATE INDEX IF NOT EXISTS {table}_metadata_idx"
                f"  ON {table} USING gin (metadata)"
            ),
        ]

        with self._engine.connect() as conn:
            for stmt in ddl_statements:
                conn.execute(text(stmt))
            conn.commit()

    # ── 核心 CRUD ──────────────────────────────────────────────────

    def add_documents(
        self, nodes: list[TextNode], batch_size: int | None = None, **kwargs
    ) -> list[str]:
        if not nodes:
            return []

        expected_dim = self.params.shared_params.embedding_dimension
        ids = []
        rows = []
        for node in nodes:
            node_id = node.node_id or generate_uuid()
            if node.embedding and len(node.embedding) != expected_dim:
                raise ValueError(
                    f"向量维度不匹配: 期望 {expected_dim}, "
                    f"实际 {len(node.embedding)}, node_id={node_id}"
                )
            ids.append(node_id)
            rows.append(
                {
                    "id": node_id,
                    "document": node.text,
                    "metadata": json.dumps(node.metadata, ensure_ascii=False),
                    "embedding": str(node.embedding),
                }
            )

        table = self._table_name
        # ON CONFLICT DO NOTHING：chunk_id 确定性生成，重复入库时幂等跳过，
        # 避免主键冲突导致整批插入回滚（启动重建 / 去重击穿场景）
        insert_sql = (
            f"INSERT INTO {table} (id, document, metadata, embedding) "  # nosec B608 — table 经 _sanitize_identifier 白名单校验
            "VALUES (:id, :document, :metadata::jsonb, :embedding::vector) "
            "ON CONFLICT (id) DO NOTHING"
        )

        try:
            with self._engine.connect() as conn:
                for row in rows:
                    conn.execute(text(insert_sql), row)
                conn.commit()
        except Exception as e:
            self.logger.error(
                "[PGVectorStore] 添加文档失败: %s (%s)",
                type(e).__name__,
                str(e)[:200],
            )
            raise

        self.logger.info("[PGVectorStore] 添加 %d 个文档成功", len(nodes))
        return ids

    def similarity_search_by_vector(
        self,
        query_vector: list[float],
        k: int,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:

        table = self._table_name
        vec_literal = str(query_vector)

        where_clause, where_params = self._build_metadata_filter(metadata_filter)
        sql = (
            "SELECT id, document, metadata, embedding <=> :vec::vector AS distance "
            f"FROM {table} "
            f"{where_clause} "  # nosec B608 — where_clause 用 bind params
            "ORDER BY embedding <=> :vec::vector "
            "LIMIT :limit"
        )

        params = {"vec": vec_literal, "limit": k}
        params.update(where_params)

        try:
            with self._engine.connect() as conn:
                rows = conn.execute(text(sql), params).mappings().all()

            nodes = []
            for row in rows:
                distance = row["distance"]
                metadata = row["metadata"]
                node = TextNode(
                    id_=row["id"],
                    text=row["document"],
                    metadata=json.loads(metadata)
                    if isinstance(metadata, str)
                    else metadata,
                )
                node.metadata["_score"] = 1 - distance
                nodes.append(node)
            return nodes
        except Exception as e:
            self.logger.error(
                "[PGVectorStore] 向量检索失败: %s (%s)",
                type(e).__name__,
                str(e)[:200],
            )
            return []

    def delete_by_metadata(self, metadata_filter: dict[str, Any], **kwargs) -> int:
        """按元数据删除匹配文档，返回删除数量。

        使用 DELETE ... RETURNING 合并为单次查询。
        失败时抛 RuntimeError 而非静默返回 0，确保调用方可感知。
        """

        table = self._table_name
        where_clause, where_params = self._build_metadata_filter(metadata_filter)

        try:
            with self._engine.connect() as conn:
                delete_sql = f"DELETE FROM {table} {where_clause} RETURNING id"  # nosec B608 — table 校验 + where_clause 用 bind params
                rows = conn.execute(text(delete_sql), where_params).fetchall()
                conn.commit()

            return len(rows)
        except Exception as e:
            self.logger.error(
                "[PGVectorStore] 按元数据删除失败: %s (%s)",
                type(e).__name__,
                str(e)[:200],
            )
            raise RuntimeError(f"向量库删除失败: {type(e).__name__}") from e

    def update_metadata_by_filter(
        self,
        metadata_filter: dict[str, Any],
        updates: dict[str, Any] | None = None,
        remove_keys: set[str] | None = None,
    ) -> int:
        """通用 metadata 更新，支持按 metadata 条件更新或移除字段。"""
        vector_table = table(
            self._table_name,
            column("id"),
            column("metadata", JSONB),
        )
        metadata_column = vector_table.c.metadata
        metadata_expr = metadata_column
        for key in remove_keys or set():
            metadata_expr = metadata_expr.op("-")(literal(key))
        if updates:
            metadata_expr = metadata_expr.op("||")(literal(updates, type_=JSONB))
        statement = (
            update(vector_table)
            .where(metadata_column.contains(literal(metadata_filter, type_=JSONB)))
            .values(metadata=metadata_expr)
            .returning(vector_table.c.id)
        )
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(statement).fetchall()  # nosec B608 — SQLAlchemy Core 表达式；表名已由 _sanitize_identifier 白名单校验
                conn.commit()
            return len(rows)
        except Exception as e:
            self.logger.error(
                "[PGVectorStore] 更新 metadata 失败: %s (%s)",
                type(e).__name__,
                str(e)[:200],
            )
            raise RuntimeError(f"向量库 metadata 更新失败: {type(e).__name__}") from e

    def get_by_metadata(
        self, metadata_filter: dict[str, Any], **kwargs
    ) -> list[TextNode]:
        """按元数据查询。不缓存：调用方（ingest 去重、constructor）可能修改返回节点。"""

        table = self._table_name
        where_clause, where_params = self._build_metadata_filter(metadata_filter)

        try:
            sql = text(f"SELECT id, document, metadata FROM {table} {where_clause}")  # nosec B608 — table 校验 + where_clause 用 bind params
            with self._engine.connect() as conn:
                rows = conn.execute(sql, where_params).mappings().all()

            return [
                TextNode(
                    id_=row["id"],
                    text=row["document"],
                    metadata=json.loads(row["metadata"])
                    if isinstance(row["metadata"], str)
                    else row["metadata"],
                )
                for row in rows
            ]
        except Exception as e:
            self.logger.error(
                "[PGVectorStore] 元数据查询失败: %s (%s)",
                type(e).__name__,
                str(e)[:200],
            )
            return []

    def get_distinct_metadata_values(self, key: str) -> set[str] | None:
        """返回指定 metadata 字段的所有非空字符串值。

        单条聚合查询，走 metadata 上的 GIN 索引。
        刻意不复用 get_by_metadata：后者异常时返回 []，调用方可能把
        "查询失败"误判成"字段没有值"。查询失败返回 None。
        """
        table = self._table_name
        try:
            sql = text(
                f"SELECT DISTINCT metadata->>:metadata_key AS value FROM {table} "  # nosec B608 — table 经 _sanitize_identifier 校验
                "WHERE metadata ? :metadata_key"
            )
            with self._engine.connect() as conn:
                rows = conn.execute(sql, {"metadata_key": key}).mappings().all()
        except Exception as e:
            self.logger.error(
                "[PGVectorStore] 查询 metadata distinct 值失败 | key=%s: %s (%s)",
                key,
                type(e).__name__,
                str(e)[:200],
            )
            return None
        return {row["value"] for row in rows if row["value"]}

    def get_by_metadata_batch(
        self,
        filters: list[dict[str, Any]],
        **kwargs,
    ) -> list[TextNode]:
        """批量元数据查询（OR 语义：匹配任意一个 filter 的文档）。

        将 N 个独立查询合并为 1 次 SQL，SectionReconstructor 场景下
        显著减少数据库查询次数。
        不缓存：返回的节分片后续会被 constructor 合并修改，缓存会导致过期数据。
        """
        if not filters:
            return []

        if len(filters) == 1:
            return self.get_by_metadata(filters[0])

        table = self._table_name
        try:
            # 构建 OR 条件的 WHERE 子句
            or_clauses = []
            or_params: dict[str, Any] = {}
            for idx, f in enumerate(filters):
                clause, params = self._build_single_metadata_clause(f, suffix=f"b{idx}")
                or_clauses.append(clause)
                or_params.update(params)

            where_str = _SQL_OR.join(or_clauses)
            sql = text(f"SELECT id, document, metadata FROM {table} WHERE {where_str}")  # nosec B608 — table 校验 + where_str 用 bind params

            with self._engine.connect() as conn:
                rows = conn.execute(sql, or_params).mappings().all()

            return [
                TextNode(
                    id_=row["id"],
                    text=row["document"],
                    metadata=json.loads(row["metadata"])
                    if isinstance(row["metadata"], str)
                    else row["metadata"],
                )
                for row in rows
            ]
        except Exception as e:
            self.logger.error(
                "[PGVectorStore] 批量元数据查询失败: %s (%s)",
                type(e).__name__,
                str(e)[:200],
            )
            return []

    def count(self, **kwargs) -> int:

        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {self._table_name}"))  # nosec B608 — _table_name 经 _sanitize_identifier 校验
                return result.scalar_one()
        except Exception as e:
            self.logger.error(
                "[PGVectorStore] 获取总数失败: %s (%s)",
                type(e).__name__,
                str(e)[:200],
            )
            return 0

    # ── 生命周期 ────────────────────────────────────────────────────

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._engine is not None:
            self._engine.dispose()
        self.logger.info("[PGVectorStore] 资源已释放")

    # ── 元数据过滤 SQL 构建 ────────────────────────────────────────

    def _build_metadata_filter(
        self, metadata_filter: dict[str, Any] | None
    ) -> tuple[str, dict[str, Any]]:
        """根据 metadata_filter 构建 WHERE 子句。

        支持操作符：
          {"key": "value"}            → metadata->>'key' = 'value'     (精确匹配)
          {"key": {"$eq": "value"}}   → metadata->>'key' = 'value'
          {"key": {"$ne": "value"}}   → metadata->>'key' != 'value'
          {"key": {"$in": ["a","b"]}} → metadata->>'key' IN ('a', 'b')
          {"key": {"$exists": true}}  → metadata ? 'key'
        """
        if not metadata_filter:
            return "", {}

        clauses, params = self._build_metadata_clauses(metadata_filter)
        where_str = _SQL_AND.join(clauses)
        return f"WHERE {where_str}", params

    def _build_metadata_clauses(
        self, metadata_filter: dict[str, Any], prefix: str = "p"
    ) -> tuple[list[str], dict[str, Any]]:
        """递归构建 WHERE 子句列表（支持 $and / $or / $not）。"""
        clauses: list[str] = []
        params: dict[str, Any] = {}

        for key, value in metadata_filter.items():
            if key == "$and":
                sub_clauses = []
                for i, sub_filter in enumerate(value):
                    sc, sp = self._build_metadata_clauses(
                        sub_filter, prefix=f"{prefix}_and{i}"
                    )
                    sub_clauses.extend(sc)
                    params.update(sp)
                if sub_clauses:
                    clauses.append(f"({_SQL_AND.join(sub_clauses)})")
            elif key == "$or":
                sub_clauses = []
                for i, sub_filter in enumerate(value):
                    sc, sp = self._build_metadata_clauses(
                        sub_filter, prefix=f"{prefix}_or{i}"
                    )
                    sub_clauses.extend(sc)
                    params.update(sp)
                if sub_clauses:
                    clauses.append(f"({_SQL_OR.join(sub_clauses)})")
            elif key == "$not":
                sc, sp = self._build_metadata_clauses(value, prefix=f"{prefix}_not")
                if sc:
                    clauses.append(f"NOT ({_SQL_AND.join(sc)})")
                    params.update(sp)
            else:
                # 字段级过滤：校验 key 为合法标识符，防止 SQL 注入
                if not _IDENTIFIER_PATTERN.match(str(key)):
                    raise ValueError(
                        f"非法 metadata 字段名: '{key}'。仅允许字母、数字、下划线。"
                    )
                param_name = f"{prefix}_{key}"
                if isinstance(value, dict):
                    # 操作符
                    for op, op_val in value.items():
                        if op == "$eq":
                            clauses.append(
                                f"metadata->>:{param_name}_k = :{param_name}_v"
                            )
                            params[f"{param_name}_k"] = key
                            params[f"{param_name}_v"] = str(op_val)
                        elif op == "$ne":
                            clauses.append(
                                f"metadata->>:{param_name}_k != :{param_name}_v"
                            )
                            params[f"{param_name}_k"] = key
                            params[f"{param_name}_v"] = str(op_val)
                        elif op == "$in":
                            if not op_val:
                                # 空列表：永远不匹配
                                clauses.append("FALSE")
                                continue
                            in_placeholders = []
                            for i, item in enumerate(op_val):
                                ph = f"{param_name}_v{i}"
                                in_placeholders.append(f":{ph}")
                                params[ph] = str(item)
                            clauses.append(
                                "metadata->>:{}_k IN ({})".format(
                                    param_name, ", ".join(in_placeholders)
                                )
                            )
                            params[f"{param_name}_k"] = key
                        elif op == "$exists":
                            if op_val:
                                clauses.append(f"metadata ? :{param_name}_k")
                                params[f"{param_name}_k"] = key
                            else:
                                clauses.append(f"NOT (metadata ? :{param_name}_k)")
                                params[f"{param_name}_k"] = key
                        else:
                            self.logger.warning("不支持的操作符: %s", op)
                else:
                    # 精确匹配
                    clauses.append(f"metadata->>:{param_name}_k = :{param_name}_v")
                    params[f"{param_name}_k"] = key
                    params[f"{param_name}_v"] = str(value)

        return clauses, params

    def _build_single_metadata_clause(
        self, metadata_filter: dict[str, Any], suffix: str = ""
    ) -> tuple[str, dict[str, Any]]:
        """构建单个 metadata filter 的 WHERE 子句（用于 OR 合并）。"""
        clauses, params = self._build_metadata_clauses(metadata_filter, prefix=suffix)
        return f"({_SQL_AND.join(clauses)})", params
