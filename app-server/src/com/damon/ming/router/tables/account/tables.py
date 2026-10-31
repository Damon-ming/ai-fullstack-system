# app-server/src/com/damon/ming/router/tables/account/tables.py
"""
账号体系表定义 —— users / devices / sessions。

提供：
  - users / devices / sessions: Table 对象
  - UserRow / DeviceRow / SessionRow: 查询结果 dataclass
  - create_account_tables(db_conn): 建表 + 账号体系索引
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Column, String, Table, Text
from src.com.damon.ming.router.tables.base import _NOW, metadata

# ---------------------------------------------------------------------------
# users 表
# ---------------------------------------------------------------------------

users = Table(
    "users",
    metadata,
    Column("token", String(64), primary_key=True),
    Column("phone", String(32), nullable=False, unique=True),
    Column("name", String(64), nullable=False, server_default=""),
    Column("created_at", nullable=False, server_default=_NOW),
    # SECURITY: token TTL（P1-7 修复）
    # expires_at — 滚动过期：30 天不活跃则失效
    # hard_expires_at — 绝对过期：90 天强制重新登录
    Column("expires_at", nullable=False),
    Column("hard_expires_at", nullable=False),
)


@dataclass(frozen=True)
class UserRow:
    token: str
    phone: str
    name: str = ""
    created_at: datetime | None = None
    expires_at: datetime | None = None
    hard_expires_at: datetime | None = None


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
    Column("created_at", nullable=False, server_default=_NOW),
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
    Column("created_at", nullable=False, server_default=_NOW),
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
# 索引 DDL
# ---------------------------------------------------------------------------

_ACCOUNT_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_token_device ON sessions (token, device_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions (token)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_device ON sessions (device_id)",
]


def create_account_tables(db_conn) -> None:
    """创建账号体系表 + 索引（幂等）。"""
    metadata.create_all(db_conn.engine)
    for ddl in _ACCOUNT_INDEX_DDL:
        db_conn.execute(ddl, commit=True)
