# app-server/src/com/damon/ming/router/tables/history/tables.py
"""
对话历史表定义 —— history_conversations。

提供：
  - history_conversations: Table 对象
  - HistoryConversationRow: 查询结果 dataclass
  - create_history_tables(db_conn): 建表 + 对话历史索引
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import JSON, Column, Integer, String, Table, UniqueConstraint
from src.com.damon.ming.router.tables.base import _NOW, metadata

# ---------------------------------------------------------------------------
# history_conversations 表
# ---------------------------------------------------------------------------

history_conversations = Table(
    "history_conversations",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("token", String(64), nullable=False),
    Column("title", String(200), nullable=False),
    Column("messages", JSON, nullable=False),
    Column("msg_count", Integer, nullable=False, server_default="0"),
    Column("created_at", nullable=False, server_default=_NOW),
    Column("updated_at", nullable=False, server_default=_NOW),
    UniqueConstraint("token", "title", name="uq_history_token_title"),
)


@dataclass(frozen=True)
class HistoryConversationRow:
    id: str
    token: str
    title: str
    messages: list | None = None
    msg_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# 索引 DDL
# ---------------------------------------------------------------------------

_HISTORY_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_history_token ON history_conversations (token)",
    "CREATE INDEX IF NOT EXISTS idx_history_updated ON history_conversations (updated_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_history_token_title ON history_conversations (token, title)",
]


def create_history_tables(db_conn) -> None:
    """创建对话历史表 + 索引（幂等）。"""
    metadata.create_all(db_conn.engine)
    for ddl in _HISTORY_INDEX_DDL:
        db_conn.execute(ddl, commit=True)
