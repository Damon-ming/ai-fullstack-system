# app-server/src/com/damon/ming/encryption/key_store/pg_key_store.py
"""
PostgreSQL 密钥存储实现 —— 会话密钥持久化到数据库。

依赖 db 模块（src.com.damon.ming.db）处理连接管理和 SQL 执行，
本文件只定义"加密_sessions"表的表结构和 SQL 语句。

表结构：
  encryption_sessions (
    key_id       VARCHAR(64)  PRIMARY KEY,
    aes_key_enc  TEXT         NOT NULL,  -- KEK 加密后的 AES 密钥 (base64)
    device_id    VARCHAR(128) NOT NULL DEFAULT '',
    created_at   TIMESTAMP    NOT NULL,
    expires_at   TIMESTAMP    NOT NULL
  )

索引：
  - idx_enc_sessions_device_id: 按设备查找
  - idx_enc_sessions_expires:   过期清理

安全说明：
  - aes_key_enc 是 KEK 加密后的密文，DB 泄露不会直接暴露 AES 密钥
  - KEK 从 MASTER_KEY 环境变量派生，不落盘
  - 设备再次注册时覆盖旧记录（一个设备一条活跃会话）
"""

from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.db.db_connection import DbConnection
from src.com.damon.ming.db.db_migration import DbMigration
from src.com.damon.ming.encryption.key_store.base_key_store import (
    BaseKeyStore,
    StoredSession,
)

# ---------------------------------------------------------------------------
# 迁移定义（由 DbMigration 执行）
# ---------------------------------------------------------------------------

_MIGRATION_ID = "001_encryption_sessions"
_MIGRATION_DDL = """
CREATE TABLE IF NOT EXISTS encryption_sessions (
    key_id       VARCHAR(64)  PRIMARY KEY,
    aes_key_enc  TEXT         NOT NULL,
    device_id    VARCHAR(128) NOT NULL DEFAULT '',
    created_at   TIMESTAMP    NOT NULL,
    expires_at   TIMESTAMP    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enc_sessions_device_id ON encryption_sessions (device_id);
CREATE INDEX IF NOT EXISTS idx_enc_sessions_expires ON encryption_sessions (expires_at);
"""

# ---------------------------------------------------------------------------
# SQL 语句
# ---------------------------------------------------------------------------

_SAVE_OR_UPDATE = """
INSERT INTO encryption_sessions (key_id, aes_key_enc, device_id, created_at, expires_at)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (key_id) DO UPDATE SET
    aes_key_enc = EXCLUDED.aes_key_enc,
    device_id   = EXCLUDED.device_id,
    created_at  = EXCLUDED.created_at,
    expires_at  = EXCLUDED.expires_at;
"""

_GET_BY_KEY = """
SELECT key_id, aes_key_enc, device_id, created_at, expires_at
FROM encryption_sessions
WHERE key_id = %s AND expires_at > NOW();
"""

_GET_BY_DEVICE = """
SELECT key_id, aes_key_enc, device_id, created_at, expires_at
FROM encryption_sessions
WHERE device_id = %s AND expires_at > NOW()
ORDER BY created_at DESC
LIMIT 1;
"""

_DELETE_BY_KEY = """
DELETE FROM encryption_sessions WHERE key_id = %s;
"""

_DELETE_BY_DEVICE = """
DELETE FROM encryption_sessions WHERE device_id = %s;
"""

_CLEANUP_EXPIRED = """
DELETE FROM encryption_sessions WHERE expires_at <= NOW();
"""

_COUNT = """
SELECT COUNT(*) FROM encryption_sessions;
"""


class PgKeyStore(BaseKeyStore):
    """PostgreSQL 密钥存储后端。

    接受一个已初始化的 DbConnection，或使用 DbConfig 自动创建。

    用法：
        # 方式一：传入 DbConnection（与项目其他模块共享连接池）
        db_conn = DbConnection(DbConfig.from_env())
        db_conn.initialize()
        store = PgKeyStore(db_conn)
        store.initialize()

        # 方式二：传入连接字符串（独立连接）
        store = PgKeyStore.from_connection_string("postgresql://...")
        store.initialize()
    """

    def __init__(self, db_connection: DbConnection) -> None:
        self._db = db_connection
        self._migration = DbMigration(db_connection)
        self._migration.register(_MIGRATION_ID, _MIGRATION_DDL)

    @staticmethod
    def from_connection_string(conn_string: str) -> "PgKeyStore":
        """从连接字符串创建 PgKeyStore（使用独立连接）。"""
        config = DbConfig(connection_string=conn_string)
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
        self._migration.apply_all()

    def save_session(self, session: StoredSession) -> None:
        self._db.execute(
            _SAVE_OR_UPDATE,
            (
                session.key_id,
                session.aes_key_enc,
                session.device_id,
                session.created_at,
                session.expires_at,
            ),
        )

    def get_session(self, key_id: str) -> StoredSession | None:
        rows = self._db.execute(_GET_BY_KEY, (key_id,), commit=False, fetch=True)
        if not rows:
            return None
        row = rows[0]
        return StoredSession(
            key_id=row[0],
            aes_key_enc=row[1],
            device_id=row[2],
            created_at=row[3],
            expires_at=row[4],
        )

    def get_session_by_device(self, device_id: str) -> StoredSession | None:
        rows = self._db.execute(
            _GET_BY_DEVICE, (device_id,), commit=False, fetch=True
        )
        if not rows:
            return None
        row = rows[0]
        return StoredSession(
            key_id=row[0],
            aes_key_enc=row[1],
            device_id=row[2],
            created_at=row[3],
            expires_at=row[4],
        )

    def remove_session(self, key_id: str) -> None:
        self._db.execute(_DELETE_BY_KEY, (key_id,))

    def remove_by_device(self, device_id: str) -> None:
        self._db.execute(_DELETE_BY_DEVICE, (device_id,))

    def cleanup_expired(self) -> int:
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_CLEANUP_EXPIRED)
                count = cur.rowcount
            conn.commit()
            return count
        finally:
            self._db._return_conn(conn)

    def count(self) -> int:
        rows = self._db.execute(_COUNT, commit=False, fetch=True)
        return rows[0][0] if rows else 0
