# app-server/src/com/damon/ming/app/encryption/key_store.py
"""
数据库密钥存储实现 —— 业务层存储后端。

本文件从 router/encryption/ 迁移到 app/encryption/，
因为存储实现属于业务层，不属于路由层。

关联：
  devices 表由 account_schema.py 管理，本模块不再重复建表。
  encryption_sessions 通过 session_id 与 sessions 表关联。

表定义统一在 app/tables.py，本文件只负责业务逻辑和调用。
"""

from sqlalchemy import text
from src.com.damon.ming.app.encryption.base_key_store import (
    BaseKeyStore,
    StoredSession,
)
from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.db.db_connection import DbConnection
from src.com.damon.ming.router.tables.encryption import (
    encryption_sessions,
)


class PgKeyStore(BaseKeyStore):
    """密钥存储后端（基于 SQLAlchemy，支持多数据库后端）。

    在 BaseKeyStore 纯 key_id 接口之上，扩展了会话维度索引（业务需求）。

    用法：
        # 方式一：传入 DbConnection（与项目其他模块共享连接池）
        db_conn = DbConnection(db_config)
        db_conn.initialize()
        store = PgKeyStore(db_conn)
        store.initialize()

        # 方式二：传入 SQLAlchemy URL（独立连接，测试用）
        store = PgKeyStore.from_url("postgresql://...")
        store.initialize()
    """

    def __init__(self, db_connection: DbConnection) -> None:
        self._db = db_connection

    @staticmethod
    def from_url(url: str) -> "PgKeyStore":
        """从 SQLAlchemy URL 创建 PgKeyStore（使用独立连接，测试用）。"""
        config = DbConfig(url=url)
        db_conn = DbConnection(config)
        db_conn.initialize()
        return PgKeyStore(db_conn)

    @staticmethod
    def from_config(config: DbConfig) -> "PgKeyStore":
        """从 DbConfig 创建 PgKeyStore（使用独立连接，测试用）。"""
        db_conn = DbConnection(config)
        db_conn.initialize()
        return PgKeyStore(db_conn)

    def initialize(self) -> None:
        """建表 + 建索引（幂等）。

        DDL 在 tables.py 的 create_all_tables() 中统一管理，
        此处无需重复执行。
        """

    def save_session(self, session: StoredSession, session_id: str = "") -> None:
        """保存会话记录。session_id 为业务层扩展字段，一步写入。

        同一 key_id 重复保存 → ON CONFLICT 覆盖，结果幂等。

        .. deprecated::
            使用 replace_session 原子替换，统一事务风格。
            保留本方法仅供历史兼容，新代码不应调用。
        """
        with self._db.transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO encryption_sessions "
                    "(key_id, aes_key_enc, session_id, created_at, expires_at) "
                    "VALUES (:kid, :enc, :sid, :cat, :eat) "
                    "ON CONFLICT (key_id) DO UPDATE SET "
                    "aes_key_enc = EXCLUDED.aes_key_enc, session_id = EXCLUDED.session_id, "
                    "created_at = EXCLUDED.created_at, expires_at = EXCLUDED.expires_at"
                ),
                {
                    "kid": session.key_id,
                    "enc": session.aes_key_enc,
                    "sid": session_id,
                    "cat": session.created_at,
                    "eat": session.expires_at,
                },
            )

    def replace_session(
        self,
        session_id: str,
        new_stored: StoredSession | None = None,
    ) -> None:
        """原子地替换某 session_id 关联的加密会话。

        删除该 session_id 的所有旧记录，可选插入新记录。
        两者在同一事务中，崩溃时自动 rollback。

        用法：
          - 一次性替换：replace_session(sid, new_stored)。
          - 仅删除：replace_session(sid, None)。
        """
        with self._db.transaction() as conn:
            conn.execute(
                text("DELETE FROM encryption_sessions WHERE session_id = :sid"),
                {"sid": session_id},
            )
            if new_stored is not None:
                conn.execute(
                    text(
                        "INSERT INTO encryption_sessions "
                        "(key_id, aes_key_enc, session_id, created_at, expires_at) "
                        "VALUES (:kid, :enc, :sid, :cat, :eat)"
                    ),
                    {
                        "kid": new_stored.key_id,
                        "enc": new_stored.aes_key_enc,
                        "sid": session_id,
                        "cat": new_stored.created_at,
                        "eat": new_stored.expires_at,
                    },
                )

    def get_session(
        self, key_id: str, session_id: str | None = None
    ) -> StoredSession | None:
        query = encryption_sessions.select().where(
            encryption_sessions.c.key_id == key_id,
            encryption_sessions.c.expires_at > text("NOW()"),
        )
        # 归属校验：session_id 非空时仅返回属于该 session_id 的记录
        if session_id:
            query = query.where(encryption_sessions.c.session_id == session_id)
        with self._db.engine.connect() as conn:
            result = conn.execute(query)
            row = result.fetchone()
        if row is None:
            return None
        return StoredSession(
            key_id=row.key_id,
            aes_key_enc=row.aes_key_enc,
            session_id=row.session_id or "",
            created_at=row.created_at,
            expires_at=row.expires_at,
        )

    def remove_session(self, key_id: str) -> None:
        """按 key_id 删除单条加密记录。"""
        with self._db.transaction() as conn:
            conn.execute(
                text("DELETE FROM encryption_sessions WHERE key_id = :kid"),
                {"kid": key_id},
            )

    def cleanup_expired(self) -> int:
        with self._db.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM encryption_sessions WHERE expires_at <= NOW()")
            )
            return result.rowcount

    def count(self) -> int:
        with self._db.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM encryption_sessions"))
            return result.scalar() or 0
