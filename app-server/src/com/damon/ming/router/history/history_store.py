"""
对话历史 存储层。

职责：
  - 会话（history_conversations）与轮次（history_turns）的 CRUD
  - 按 token 隔离，不同用户互不干扰
  - 分页列表查询（不含轮次正文，按 updated_at 倒序）
  - 详情查询（会话 + 轮次列表，按 query_at 升序）
  - 服务端 chat 链路写入（append_turn：轮次纯 INSERT，无读改写竞态）

存储：通过共享连接池持久化。
"""

import uuid
from datetime import datetime

from src.com.damon.ming.db.db_connection import get_default_db
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.tables.history import (
    HistoryConversationRow,
    HistoryDetailRow,
    HistoryTurnRow,
)
from src.com.damon.ming.utils.time import now

logger = pin("history.store")


def _db():
    return get_default_db()


# ---------------------------------------------------------------------------
# 列表 & 分页
# ---------------------------------------------------------------------------


def list_history(
    token: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[HistoryConversationRow], int]:
    """分页查询会话列表（不含轮次正文），按 updated_at 倒序。

    返回 (items, total)。
    """
    offset = (page - 1) * page_size

    count_rows = _db().execute(
        "SELECT COUNT(*) FROM history_conversations WHERE token = :token",
        {"token": token},
        commit=False,
        fetch=True,
    )
    total = count_rows[0][0] if count_rows else 0

    rows = _db().execute(
        "SELECT id, token, title, created_at, updated_at "
        "FROM history_conversations "
        "WHERE token = :token "
        "ORDER BY updated_at DESC "
        "LIMIT :limit OFFSET :offset",
        {"token": token, "limit": page_size, "offset": offset},
        commit=False,
        fetch=True,
    )

    items = [
        HistoryConversationRow(
            id=r[0],
            token=r[1],
            title=r[2],
            created_at=r[3],
            updated_at=r[4],
        )
        for r in (rows or [])
    ]
    return items, total


# ---------------------------------------------------------------------------
# 详情
# ---------------------------------------------------------------------------


def get_history(conversation_id: str, token: str) -> HistoryDetailRow | None:
    """查询单个会话详情（含全部轮次，按提问时间升序）。"""
    conv_rows = _db().execute(
        "SELECT id, token, title, created_at, updated_at "
        "FROM history_conversations "
        "WHERE id = :id AND token = :token",
        {"id": conversation_id, "token": token},
        commit=False,
        fetch=True,
    )
    if not conv_rows:
        return None
    c = conv_rows[0]
    conversation = HistoryConversationRow(
        id=c[0],
        token=c[1],
        title=c[2],
        created_at=c[3],
        updated_at=c[4],
    )

    turn_rows = _db().execute(
        "SELECT turn_id, conversation_id, query, reasoning, content, "
        "query_at, first_token_at, reasoning_done_at, answered_at "
        "FROM history_turns "
        "WHERE conversation_id = :cid "
        "ORDER BY query_at ASC, turn_id ASC",
        {"cid": conversation_id},
        commit=False,
        fetch=True,
    )
    turns = [
        HistoryTurnRow(
            turn_id=r[0],
            conversation_id=r[1],
            query=r[2],
            reasoning=r[3],
            content=r[4],
            query_at=r[5],
            first_token_at=r[6],
            reasoning_done_at=r[7],
            answered_at=r[8],
        )
        for r in (turn_rows or [])
    ]
    return HistoryDetailRow(conversation=conversation, turns=turns)


# ---------------------------------------------------------------------------
# 写入：服务端 chat 链路（append_turn）
# ---------------------------------------------------------------------------


def append_turn(
    token: str,
    conversation_id: str,
    title: str,
    query: str,
    reasoning: str | None,
    content: str,
    query_at: datetime,
    first_token_at: datetime | None,
    reasoning_done_at: datetime | None,
    answered_at: datetime,
) -> str:
    """写入一轮问答，返回会话 id（写入被拒绝时返回空串）。

    服务端是会话数据的唯一写入方：
      - 会话不存在 → 按 conversation_id 新建
      - 会话已存在 → 仅刷新 updated_at
    会话必须属于当前 token，否则整轮写入被拒绝。

    轮次为纯 INSERT，不像旧的「读出 messages → 拼接 → 写回」那样存在
    并发覆盖竞态。
    """
    rows = _db().execute(
        "INSERT INTO history_conversations (id, token, title, created_at, updated_at) "
        "VALUES (:id, :token, :title, :answered_at, :answered_at) "
        "ON CONFLICT (id) DO UPDATE SET updated_at = EXCLUDED.updated_at "
        "WHERE history_conversations.token = EXCLUDED.token "
        "RETURNING id",
        {
            "id": conversation_id,
            "token": token,
            "title": title,
            "answered_at": answered_at,
        },
        commit=True,
        fetch=True,
    )
    if not rows:
        logger.warning(
            "会话不存在或不属于当前用户，已跳过轮次写入 | id=%s", conversation_id
        )
        return ""

    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    _db().execute(
        "INSERT INTO history_turns "
        "(turn_id, conversation_id, query, reasoning, content, "
        " query_at, first_token_at, reasoning_done_at, answered_at) "
        "VALUES (:turn_id, :conversation_id, :query, :reasoning, :content, "
        " :query_at, :first_token_at, :reasoning_done_at, :answered_at)",
        {
            "turn_id": turn_id,
            "conversation_id": conversation_id,
            "query": query,
            "reasoning": reasoning or None,
            "content": content,
            "query_at": query_at,
            "first_token_at": first_token_at,
            "reasoning_done_at": reasoning_done_at,
            "answered_at": answered_at,
        },
        commit=True,
    )
    logger.info(
        "轮次已写入 | conversation_id=%s | turn_id=%s | reasoning=%s",
        conversation_id,
        turn_id,
        "yes" if reasoning else "no",
    )
    return conversation_id


# ---------------------------------------------------------------------------
# 写入：客户端保存口径（save_history）
# ---------------------------------------------------------------------------


def save_history(
    token: str,
    conversation_id: str,
    title: str,
    turns: list[dict],
) -> HistoryDetailRow | None:
    """保存会话（客户端口径）：按 conversation_id 幂等 upsert，整体替换轮次。

    conversation_id 为空时新建会话。
    token 级时刻（first_token_at 等）客户端无法观测：query_at/answered_at
    由服务端盖章，first_token_at 留空，reasoning_done_at 仅在存在推理文本时
    以保存时刻占位。
    """
    if not conversation_id:
        conversation_id = f"conv_{uuid.uuid4().hex[:8]}"

    current = now()
    rows = _db().execute(
        "INSERT INTO history_conversations (id, token, title, created_at, updated_at) "
        "VALUES (:id, :token, :title, :now, :now) "
        "ON CONFLICT (id) DO UPDATE SET "
        "title = EXCLUDED.title, updated_at = EXCLUDED.updated_at "
        "WHERE history_conversations.token = EXCLUDED.token "
        "RETURNING id",
        {
            "id": conversation_id,
            "token": token,
            "title": title,
            "now": current,
        },
        commit=True,
        fetch=True,
    )
    # 会话已存在但属于他人时 WHERE 不命中，必须先拦住再动轮次
    if not rows:
        logger.warning(
            "会话不存在或不属于当前用户，已跳过保存 | id=%s", conversation_id
        )
        return None

    _db().execute(
        "DELETE FROM history_turns WHERE conversation_id = :cid",
        {"cid": conversation_id},
        commit=True,
    )

    cleaned = [t for t in turns if isinstance(t, dict)]
    for t in cleaned:
        reasoning = str(t.get("reasoning") or "")
        _db().execute(
            "INSERT INTO history_turns "
            "(turn_id, conversation_id, query, reasoning, content, "
            " query_at, first_token_at, reasoning_done_at, answered_at) "
            "VALUES (:turn_id, :conversation_id, :query, :reasoning, :content, "
            " :now, NULL, :reasoning_done_at, :now)",
            {
                "turn_id": f"turn_{uuid.uuid4().hex[:12]}",
                "conversation_id": conversation_id,
                "query": str(t.get("query", "")),
                "reasoning": reasoning or None,
                "content": str(t.get("content", "")),
                "now": current,
                "reasoning_done_at": current if reasoning else None,
            },
            commit=True,
        )

    logger.info(
        "会话已保存 | id=%s | title=%s | turns=%d",
        conversation_id,
        title,
        len(cleaned),
    )
    return get_history(conversation_id, token)


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


def delete_history(conversation_id: str, token: str) -> bool:
    """删除会话及其全部轮次。返回是否实际删除（False = 不存在或无权限）。"""
    rows = _db().execute(
        "SELECT id FROM history_conversations WHERE id = :id AND token = :token",
        {"id": conversation_id, "token": token},
        commit=False,
        fetch=True,
    )
    if not rows:
        return False

    # turns 与 conversations 之间是逻辑外键，需显式级联
    _db().execute(
        "DELETE FROM history_turns WHERE conversation_id = :cid",
        {"cid": conversation_id},
        commit=True,
    )
    _db().execute(
        "DELETE FROM history_conversations WHERE id = :id AND token = :token",
        {"id": conversation_id, "token": token},
        commit=True,
    )
    logger.info("历史会话已删除 | id=%s", conversation_id)
    return True
