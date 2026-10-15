# app-server/src/com/damon/ming/router/tables/encryption/tables.py
"""
加密体系表定义 —— encryption_sessions。

提供：
  - encryption_sessions: Table 对象
  - EncryptionSessionRow: 查询结果 dataclass
  - create_encryption_tables(db_conn): 建表 + 加密体系索引
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Column, String, Table, Text
from src.com.damon.ming.router.tables.base import metadata

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
# 索引 DDL
# ---------------------------------------------------------------------------

_ENCRYPTION_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_enc_sessions_session_id ON encryption_sessions (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_enc_sessions_expires ON encryption_sessions (expires_at)",
]


def create_encryption_tables(db_conn) -> None:
    """创建加密体系表 + 索引（幂等）。"""
    metadata.create_all(db_conn.engine)
    for ddl in _ENCRYPTION_INDEX_DDL:
        db_conn.execute(ddl, commit=True)
