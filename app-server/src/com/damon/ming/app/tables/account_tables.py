# app-server/src/com/damon/ming/app/tables/account_tables.py
"""
账号体系表定义 —— users / devices / sessions。

提供：
  - users / devices / sessions: Table 对象
  - UserRow / DeviceRow: 查询结果 dataclass
  - create_account_tables(db_conn): 建表 + 账号体系索引
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Table,
    Text,
)
from src.com.damon.ming.app.tables.base import _NOW, metadata

# ---------------------------------------------------------------------------
# users 表
# ---------------------------------------------------------------------------

public_user_id_seq = Sequence(
    "users_public_id_seq", start=100000, maxvalue=999999, metadata=metadata
)

users = Table(
    "users",
    metadata,
    Column(
        "user_id",
        Integer,
        primary_key=True,
        server_default=public_user_id_seq.next_value(),
    ),
    # phone 保存 FieldEncryptor 密文；phone_idx 用于等值查找和唯一约束。
    Column("phone", String(256), nullable=False),
    Column("phone_idx", String(64), nullable=False, unique=True),
    Column("password", String(128), nullable=False, server_default=""),
    Column("name", String(64), nullable=False),
    Column("nickname", String(64), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=_NOW,
    ),
    CheckConstraint(
        "user_id BETWEEN 100000 AND 999999", name="ck_users_user_id_six_digits"
    ),
)


@dataclass(frozen=True)
class UserRow:
    user_id: int
    phone: str
    password: str = ""
    name: str = ""
    nickname: str = ""
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
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=_NOW,
    ),
)


@dataclass(frozen=True)
class DeviceRow:
    device_id: str
    ua_hash: str
    raw_ua: str = ""
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# sessions 表
# ---------------------------------------------------------------------------

sessions = Table(
    "sessions",
    metadata,
    Column("session_id", String(64), primary_key=True),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.user_id", onupdate="CASCADE"),
        nullable=False,
    ),
    Column("device_id", String(64), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=_NOW,
    ),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    # 保存随机会话 token 的 SHA-256 摘要，原文只在登录时返回客户端。
    Column("token", String(64), nullable=False, unique=True),
)


# ---------------------------------------------------------------------------
# 索引 DDL
# ---------------------------------------------------------------------------

_ACCOUNT_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_device ON sessions (user_id, device_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_device ON sessions (device_id)",
]


def create_account_tables(db_conn) -> None:
    """创建账号体系表 + 索引（幂等）。"""
    metadata.create_all(db_conn.engine)
    for ddl in _ACCOUNT_INDEX_DDL:
        db_conn.execute(ddl, commit=True)
