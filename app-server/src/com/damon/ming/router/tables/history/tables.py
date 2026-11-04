# app-server/src/com/damon/ming/router/tables/history/tables.py
"""
对话历史表定义 —— history_conversations（会话）+ history_turns（轮次）。

提供：
  - history_conversations / history_turns: Table 对象
  - HistoryConversationRow / HistoryTurnRow / HistoryDetailRow: 查询结果 dataclass
  - create_history_tables(db_conn): 建表 + 对话历史索引

设计：
  会话与轮次分离。会话只承载标题与生命周期；轮次承载一轮问答的提问、
  推理、正文与四个时间点，便于后续做时延分析与检索。
  两表之间只保留逻辑外键（conversation_id），不建 DB FOREIGN KEY。
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Table, Text
from src.com.damon.ming.router.tables.base import _NOW, metadata

# ---------------------------------------------------------------------------
# history_conversations 表 —— 会话（线程）
# ---------------------------------------------------------------------------

history_conversations = Table(
    "history_conversations",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("token", String(64), nullable=False),
    Column("title", String(200), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=_NOW),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=_NOW),
)


@dataclass(frozen=True)
class HistoryConversationRow:
    id: str
    token: str
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# history_turns 表 —— 一轮问答
# ---------------------------------------------------------------------------

history_turns = Table(
    "history_turns",
    metadata,
    Column("turn_id", String(64), primary_key=True),
    Column("conversation_id", String(64), nullable=False),
    Column("query", Text, nullable=False),
    # 推理走模型原生通道，未开启推理时为 NULL
    Column("reasoning", Text, nullable=True),
    Column("content", Text, nullable=False),
    # 本轮异常提示（用户可见文案，不含堆栈/错误码/日志）：
    # 失败 / 中断轮次存放统一提示，成功轮次为 NULL
    Column("error_msg", Text, nullable=True),
    # 四个时间点存「时刻」而非「时长」，时长由查询方派生：
    #   TTFT       = first_token_at - query_at
    #   推理耗时   = reasoning_done_at - first_token_at
    #   正文耗时   = answered_at - reasoning_done_at
    #   端到端耗时 = answered_at - query_at
    Column("query_at", DateTime(timezone=True), nullable=False),
    # 首个 token 时刻（TTFT 基准）；非流式调用测不到，为 NULL
    Column("first_token_at", DateTime(timezone=True), nullable=True),
    # 最后一个推理 token 时刻；未开启推理时为 NULL
    Column("reasoning_done_at", DateTime(timezone=True), nullable=True),
    Column("answered_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class HistoryTurnRow:
    turn_id: str
    conversation_id: str
    query: str
    content: str
    reasoning: str | None = None
    error_msg: str | None = None
    query_at: datetime | None = None
    first_token_at: datetime | None = None
    reasoning_done_at: datetime | None = None
    answered_at: datetime | None = None


@dataclass(frozen=True)
class HistoryDetailRow:
    """会话 + 轮次列表（详情查询结果）。"""

    conversation: HistoryConversationRow
    turns: list[HistoryTurnRow]


# ---------------------------------------------------------------------------
# 索引 DDL
# ---------------------------------------------------------------------------

_HISTORY_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_history_token ON history_conversations (token)",
    "CREATE INDEX IF NOT EXISTS idx_history_updated ON history_conversations (updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_history_turns_conversation ON history_turns (conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_history_turns_query_at ON history_turns (query_at)",
    # 增量列：已存在的库表补 error_msg（幂等）
    "ALTER TABLE history_turns ADD COLUMN IF NOT EXISTS error_msg TEXT",
]


def create_history_tables(db_conn) -> None:
    """创建对话历史表 + 索引（幂等）。"""
    metadata.create_all(db_conn.engine)
    for ddl in _HISTORY_DDL:
        db_conn.execute(ddl, commit=True)
