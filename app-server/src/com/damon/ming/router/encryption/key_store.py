# app-server/src/com/damon/ming/router/encryption/key_store.py
"""
数据库密钥存储实现 —— 会话密钥持久化到数据库。

本文件属于业务层（router/encryption/），在纯存储接口之上扩展了业务维度索引。

关联：
  devices 表由 account_schema.py 管理，本模块不再重复建表。
  encryption_sessions 通过 session_id 与 sessions 表关联。

表定义统一在 router/tables.py，本文件只负责业务逻辑和调用。
"""

from sqlalchemy import text
from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.db.db_connection import DbConnection
from src.com.damon.ming.encryption.key_store.base_key_store import (
    BaseKeyStore,
    StoredSession,
)
from src.com.damon.ming.router.tables.encryption import (
    encryption_sessions,
)


class PgKeyStore(BaseKeyStore):
    """密钥存储后端（基于 SQLAlchemy，支持多数据库后端）。

    在 BaseKeyStore 纯 key_id 接口之上，扩展了会话维度索引（业务需求）。

    用法：
        # 方式一：传入 DbConnection（与项目其他模块共享连接池）
        db_conn = DbConnection(db_config)  # db_config 由上层配置加载器构造
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
        """
        self._db.execute(
            "INSERT INTO encryption_sessions (key_id, aes_key_enc, session_id, created_at, expires_at) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (key_id) DO UPDATE SET "
            "aes_key_enc = EXCLUDED.aes_key_enc, session_id = EXCLUDED.session_id, "
            "created_at = EXCLUDED.created_at, expires_at = EXCLUDED.expires_at",
            (
                session.key_id,
                session.aes_key_enc,
                session_id,
                session.created_at,
                session.expires_at,
            ),
            commit=True,
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
          - 换绑：先 replace_session(sid, None) 删除旧记录，
                  再 save_session(new_stored) 插入新记录。
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

    def get_session(self, key_id: str) -> StoredSession | None:
        with self._db.engine.connect() as conn:
            result = conn.execute(
                encryption_sessions.select().where(
                    encryption_sessions.c.key_id == key_id,
                    encryption_sessions.c.expires_at > text("NOW()"),
                )
            )
            row = result.fetchone()
        if row is None:
            return None
        return StoredSession(
            key_id=row.key_id,
            aes_key_enc=row.aes_key_enc,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )

    def remove_session(self, key_id: str) -> None:
        with self._db.engine.connect() as conn:
            conn.execute(
                encryption_sessions.delete().where(
                    encryption_sessions.c.key_id == key_id
                )
            )
            conn.commit()

    def remove_by_session(self, session_id: str) -> None:
        """按会话删除所有加密记录（业务层扩展方法）。"""
        with self._db.engine.connect() as conn:
            conn.execute(
                encryption_sessions.delete().where(
                    encryption_sessions.c.session_id == session_id
                )
            )
            conn.commit()

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

    # ---------------------------------------------------------------------------
    # 业务层绑定接口（加密模块不感知，由业务层调用）
    # ---------------------------------------------------------------------------

    def bind_session(self, key_id: str, session_id: str) -> None:
        """
        将加密会话绑定到业务会话。

        .. deprecated::
            使用 save_session(stored, session_id=...) 一步写入代替，
            避免 save + bind 两步之间的竞态窗口。
            保留本方法仅供历史兼容，新代码不应调用。
        """
        with self._db.engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE encryption_sessions SET session_id = :sid WHERE key_id = :kid"
                ),
                {"sid": session_id, "kid": key_id},
            )
            conn.commit()

    def get_binding_id(self, key_id: str) -> str | None:
        """查询加密会话绑定的业务会话标识。无绑定返回空串。"""
        with self._db.engine.connect() as conn:
            result = conn.execute(
                encryption_sessions.select().where(
                    encryption_sessions.c.key_id == key_id
                )
            )
            row = result.fetchone()
        if row is None:
            return None
        return row.session_id or None
