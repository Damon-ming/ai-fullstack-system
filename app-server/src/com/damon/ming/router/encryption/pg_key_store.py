# app-server/src/com/damon/ming/router/encryption/pg_key_store.py
"""
PostgreSQL 密钥存储实现 —— 会话密钥持久化到数据库。

本文件属于业务层（router/encryption/），在纯存储接口之上扩展了业务维度索引。

关联：
  devices 表由 account_schema.py 管理，本模块不再重复建表。
  encryption_sessions 通过 session_id 与 sessions 表关联。

SQL 语句在 encryption_sql.py，本文件只负责业务逻辑和调用。
"""

from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.db.db_connection import DbConnection
from src.com.damon.ming.encryption.key_store.base_key_store import (
    BaseKeyStore,
    StoredSession,
)
from src.com.damon.ming.router.encryption.encryption_sql import (
    BIND_SESSION,
    CLEANUP_EXPIRED,
    COUNT,
    DDL_ENCRYPTION_SESSIONS,
    DELETE_BY_KEY,
    DELETE_BY_SESSION,
    GET_BINDING,
    GET_BY_KEY,
    SAVE_OR_UPDATE,
)


class PgKeyStore(BaseKeyStore):
    """密钥存储后端（基于 SQLAlchemy，支持多数据库后端）。

    在 BaseKeyStore 纯 key_id 接口之上，扩展了会话维度索引（业务需求）。

    用法：
        # 方式一：传入 DbConnection（与项目其他模块共享连接池）
        db_conn = DbConnection(DbConfig.from_env())
        db_conn.initialize()
        store = PgKeyStore(db_conn)
        store.initialize()

        # 方式二：传入 SQLAlchemy URL（独立连接）
        store = PgKeyStore.from_url("postgresql://...")
        store.initialize()
    """

    def __init__(self, db_connection: DbConnection) -> None:
        self._db = db_connection

    @staticmethod
    def from_url(url: str) -> "PgKeyStore":
        """从 SQLAlchemy URL 创建 PgKeyStore（使用独立连接）。"""
        config = DbConfig(url=url)
        db_conn = DbConnection(config)
        db_conn.initialize()
        return PgKeyStore(db_conn)

    @staticmethod
    def from_config(config: DbConfig) -> "PgKeyStore":
        """从 DbConfig 创建 PgKeyStore（使用独立连接）。"""
        db_conn = DbConnection(config)
        db_conn.initialize()
        return PgKeyStore(db_conn)

    def initialize(self) -> None:
        """建表 + 建索引（幂等）。"""
        self._db.execute(DDL_ENCRYPTION_SESSIONS, commit=True)

    def save_session(self, session: StoredSession, session_id: str = "") -> None:
        """保存会话记录。session_id 为业务层扩展字段。"""
        self._db.execute(
            SAVE_OR_UPDATE,
            (
                session.key_id,
                session.aes_key_enc,
                session_id,
                session.created_at,
                session.expires_at,
            ),
        )

    def get_session(self, key_id: str) -> StoredSession | None:
        rows = self._db.execute(GET_BY_KEY, (key_id,), commit=False, fetch=True)
        if not rows:
            return None
        row = rows[0]
        return StoredSession(
            key_id=row[0],
            aes_key_enc=row[1],
            created_at=row[3],
            expires_at=row[4],
        )

    def remove_session(self, key_id: str) -> None:
        self._db.execute(DELETE_BY_KEY, (key_id,))

    def remove_by_session(self, session_id: str) -> None:
        """按会话删除所有加密记录（业务层扩展方法）。"""
        self._db.execute(DELETE_BY_SESSION, (session_id,))

    def cleanup_expired(self) -> int:
        from sqlalchemy import text

        with self._db.transaction() as conn:
            result = conn.execute(text(CLEANUP_EXPIRED))
            return result.rowcount

    def count(self) -> int:
        rows = self._db.execute(COUNT, commit=False, fetch=True)
        return rows[0][0] if rows else 0

    # ---------------------------------------------------------------------------
    # 业务层绑定接口（加密模块不感知，由业务层调用）
    # ---------------------------------------------------------------------------

    def bind_session(self, key_id: str, session_id: str) -> None:
        """
        将加密会话绑定到业务会话。

        由业务层在 register_session 成功后调用，加密模块不感知此方法。
        session_id 在此仅是 opaque string，不解析其含义。
        """
        self._db.execute(BIND_SESSION, (session_id, key_id), commit=True)

    def get_binding_id(self, key_id: str) -> str | None:
        """查询加密会话绑定的业务会话标识。无绑定返回空串。"""
        rows = self._db.execute(GET_BINDING, (key_id,), commit=False, fetch=True)
        if not rows:
            return None
        result = rows[0][0]
        return result if result else None
