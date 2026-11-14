# app-server/src/com/damon/ming/app/encryption/key_store.py
"""
数据库密钥存储实现 —— 业务层存储后端。

本文件从 router/encryption/ 迁移到 app/encryption/，
因为存储实现属于业务层，不属于路由层。

关联：
  devices 表由 app/tables/account_tables.py 管理，本模块不再重复建表。
  encryption_sessions 表通过 session_id 与 sessions 表关联。

表定义统一在 app/tables/，本模块使用 SQLAlchemy Core 复用表对象。
"""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.com.damon.ming.app.encryption.base_key_store import (
    BaseKeyStore,
    EncryptionSessionRecord,
)
from src.com.damon.ming.app.tables.encryption_tables import encryption_sessions_table
from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.db.db_connection import DbConnection


class PgKeyStore(BaseKeyStore):
    """密钥存储后端（SQLAlchemy Core，UPSERT 使用 PostgreSQL 方言）。

    在 BaseKeyStore 纯 key_id 接口之上，扩展了会话维度索引（业务需求）。

    用法：
        # 传入 DbConnection（与项目其他模块共享连接池）
        db_conn = DbConnection(db_config)
        db_conn.initialize()
        store = PgKeyStore(db_conn)
    """

    def __init__(self, db_connection: DbConnection) -> None:
        self._db = db_connection

    @staticmethod
    def from_config(config: DbConfig) -> "PgKeyStore":
        """从 DbConfig 创建 PgKeyStore（使用独立连接，测试用）。"""
        db_conn = DbConnection(config)
        db_conn.initialize()
        return PgKeyStore(db_conn)

    def save_session(
        self, session: EncryptionSessionRecord, session_id: str = ""
    ) -> None:
        """保存会话记录。session_id 为业务层扩展字段，一步写入。

        同一 key_id 重复保存 → ON CONFLICT 覆盖，结果幂等。

        .. deprecated::
            使用 replace_session 原子替换，统一事务风格。
            保留本方法仅供历史兼容，新代码不应调用。
        """
        with self._db.transaction() as conn:
            statement = pg_insert(encryption_sessions_table).values(
                key_id=session.key_id,
                aes_key_enc=session.aes_key_enc,
                session_id=session_id,
                created_at=session.created_at,
                expires_at=session.expires_at,
            )
            conn.execute(
                statement.on_conflict_do_update(
                    index_elements=[encryption_sessions_table.c.key_id],
                    set_={
                        column: statement.excluded[column.name]
                        for column in (
                            encryption_sessions_table.c.aes_key_enc,
                            encryption_sessions_table.c.session_id,
                            encryption_sessions_table.c.created_at,
                            encryption_sessions_table.c.expires_at,
                        )
                    },
                )
            )

    def replace_session(
        self,
        session_id: str,
        new_stored: EncryptionSessionRecord | None = None,
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
                encryption_sessions_table.delete().where(
                    encryption_sessions_table.c.session_id == session_id
                )
            )
            if new_stored is not None:
                conn.execute(
                    encryption_sessions_table.insert().values(
                        key_id=new_stored.key_id,
                        aes_key_enc=new_stored.aes_key_enc,
                        session_id=session_id,
                        created_at=new_stored.created_at,
                        expires_at=new_stored.expires_at,
                    )
                )

    def get_session(
        self, key_id: str, session_id: str | None = None
    ) -> EncryptionSessionRecord | None:
        # SECURITY: 拒绝空 session_id，始终执行归属过滤（P1-1 修复）
        if not session_id:
            return None
        with self._db.engine.connect() as conn:
            result = conn.execute(
                select(encryption_sessions_table).where(
                    encryption_sessions_table.c.key_id == key_id,
                    encryption_sessions_table.c.expires_at > func.now(),
                    encryption_sessions_table.c.session_id == session_id,
                )
            )
            row = result.fetchone()
        if row is None:
            return None
        return EncryptionSessionRecord(
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
                encryption_sessions_table.delete().where(
                    encryption_sessions_table.c.key_id == key_id
                )
            )

    def cleanup_expired(self) -> int:
        with self._db.transaction() as conn:
            result = conn.execute(
                encryption_sessions_table.delete().where(
                    encryption_sessions_table.c.expires_at <= func.now()
                )
            )
            return result.rowcount

    def count(self) -> int:
        with self._db.engine.connect() as conn:
            result = conn.execute(
                select(func.count()).select_from(encryption_sessions_table)
            )
            return result.scalar() or 0
