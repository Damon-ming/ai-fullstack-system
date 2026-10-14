# app-server/src/com/damon/ming/router/tables.py
"""
数据库表定义 —— SQLAlchemy Core Table 声明 + 结果集 dataclass。

提供：
  - metadata: 共享 MetaData 实例
  - users / devices / sessions / encryption_sessions: Table 对象
  - UserRow / DeviceRow / SessionRow / EncryptionSessionRow: 查询结果 dataclass
  - create_all_tables(db_conn): 调用 metadata.create_all() 建表 + 手写索引

设计原则：
  - 简单 CRUD 用 Core API（table.select().where() / table.insert().values()）
  - 复杂语句（ON CONFLICT、多条件混合、事务内多步）仍用 raw SQL
  - 查询结果通过 dataclass 映射，替代 tuple 解包
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    Column,
    MetaData,
    String,
    Table,
    Text,
    text,
)

metadata = MetaData()

# ---------------------------------------------------------------------------
# users 表
# ---------------------------------------------------------------------------

users = Table(
    "users",
    metadata,
    Column("token", String(64), primary_key=True),
    Column("phone", String(32), nullable=False, unique=True),
    Column("created_at", nullable=False, server_default=text("NOW()")),
)


@dataclass(frozen=True)
class UserRow:
    token: str
    phone: str
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# devices 表
# ---------------------------------------------------------------------------

devices = Table(
    "devices",
    metadata,
    Column("device_id", String(64), primary_key=True),
    Column("ua_hash", String(64), nullable=False),
    Column("raw_ua", Text, nullable=False, server_default=""),
    Column("platform", String(32), nullable=False, server_default=""),
    Column("screen", String(16), nullable=False, server_default=""),
    Column("lang", String(16), nullable=False, server_default=""),
    Column("tz", String(32), nullable=False, server_default=""),
    Column("created_at", nullable=False, server_default=text("NOW()")),
)


@dataclass(frozen=True)
class DeviceRow:
    device_id: str
    ua_hash: str
    raw_ua: str = ""
    platform: str = ""
    screen: str = ""
    lang: str = ""
    tz: str = ""
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# sessions 表
# ---------------------------------------------------------------------------

sessions = Table(
    "sessions",
    metadata,
    Column("session_id", String(64), primary_key=True),
    Column("token", String(64), nullable=False),
    Column("device_id", String(64), nullable=False),
    Column("issued_ua_hash", String(64), nullable=False, server_default=""),
    Column("created_at", nullable=False, server_default=text("NOW()")),
    Column("expires_at", nullable=False),
)


@dataclass(frozen=True)
class SessionRow:
    session_id: str
    token: str
    device_id: str
    issued_ua_hash: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None


# ---------------------------------------------------------------------------
# encryption_sessions 表
# ---------------------------------------------------------------------------

encryption_sessions = Table(
    "encryption_sessions",
    metadata,
    Column("key_id", String(64), primary_key=True),
    Column("aes_key_enc", Text, nullable=False),
    Column("session_id", String(128), nullable=False, server_default=""),
    Column("created_at", nullable=False),
    Column("expires_at", nullable=False),
)


@dataclass(frozen=True)
class EncryptionSessionRow:
    key_id: str
    aes_key_enc: str
    session_id: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None


# ---------------------------------------------------------------------------
# 索引 DDL（Core 不覆盖的数据库特定语法）
# ---------------------------------------------------------------------------

_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_token_device ON sessions (token, device_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions (token)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_device ON sessions (device_id)",
    "CREATE INDEX IF NOT EXISTS idx_enc_sessions_session_id ON encryption_sessions (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_enc_sessions_expires ON encryption_sessions (expires_at)",
]


def create_all_tables(db_conn) -> None:
    """建表 + 建索引（幂等）。

    使用 metadata.create_all() 自动适配 PG/MySQL/SQLite 的类型差异，
    索引用 raw SQL 补充（IF NOT EXISTS 语法）。
    """
    metadata.create_all(db_conn.engine)
    for ddl in _INDEX_DDL:
        db_conn.execute(ddl, commit=True)
