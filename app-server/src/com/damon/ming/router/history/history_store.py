"""
对话历史 存储层。

职责：
  - 对话历史记录 CRUD（按 token 隔离，不同用户互不干扰）
  - 分页列表查询（不含消息正文，按 updated_at 倒序）
  - 按 title 幂等更新（同一 token + title 复用同一记录）
  - 详情查询（含消息正文）

存储：通过共享连接池持久化到 history_conversations 表。
"""

import json
import uuid

from src.com.damon.ming.db.db_connection import get_default_db
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.tables.history import (
    HistoryConversationRow,
)
from src.com.damon.ming.utils.time import now

logger = pin("history.store")


def _db():
    return get_default_db()


def _row_to_detail(row, messages: list | None = None) -> HistoryConversationRow:
    """将 DB 行映射为 HistoryConversationRow。"""
    if row is None:
        return None
    msgs = messages
    if msgs is None and row.messages is not None:
        msgs = row.messages if isinstance(row.messages, list) else []
    return HistoryConversationRow(
        id=row.id,
        token=row.token,
        title=row.title,
        messages=msgs,
        msg_count=row.msg_count or 0,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# 列表 & 分页
# ---------------------------------------------------------------------------


def list_history(
    token: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[HistoryConversationRow], int]:
    """分页查询历史记录列表（不含消息正文），按 updated_at 倒序。

    返回 (items, total)。
    """
    offset = (page - 1) * page_size

    # 总条数
    count_rows = _db().execute(
        "SELECT COUNT(*) FROM history_conversations WHERE token = :token",
        {"token": token},
        commit=False,
        fetch=True,
    )
    total = count_rows[0][0] if count_rows else 0

    # 分页列表 — 不取 messages 列，减少 IO
    rows = _db().execute(
        "SELECT id, title, msg_count, created_at, updated_at "
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
            token=token,
            title=r[1],
            msg_count=r[2] or 0,
            created_at=r[3],
            updated_at=r[4],
        )
        for r in (rows or [])
    ]
    return items, total


# ---------------------------------------------------------------------------
# 详情
# ---------------------------------------------------------------------------


def get_history(conversation_id: str, token: str) -> HistoryConversationRow | None:
    """查询单条历史记录详情（含消息正文）。"""
    rows = _db().execute(
        "SELECT id, token, title, messages, msg_count, created_at, updated_at "
        "FROM history_conversations "
        "WHERE id = :id AND token = :token",
        {"id": conversation_id, "token": token},
        commit=False,
        fetch=True,
    )
    if not rows:
        return None
    r = rows[0]
    messages = r[3] if isinstance(r[3], list) else (json.loads(r[3]) if r[3] else [])
    return HistoryConversationRow(
        id=r[0],
        token=r[1],
        title=r[2],
        messages=messages,
        msg_count=r[4] or 0,
        created_at=r[5],
        updated_at=r[6],
    )


# ---------------------------------------------------------------------------
# 保存（按 title 幂等更新）
# ---------------------------------------------------------------------------


def save_history(
    token: str,
    title: str,
    messages: list[dict],
) -> HistoryConversationRow:
    """保存对话历史。

    同一 token + title 已存在则更新消息和更新时间（UPSERT）；
    不存在则新建一条记录。
    消除 SELECT + INSERT/UPDATE 之间的 TOCTOU 竞态。
    返回保存后的完整记录（含消息正文）。
    """
    current = now()
    messages_json = json.dumps(messages, ensure_ascii=False)
    msg_count = len(messages)
    conversation_id = str(uuid.uuid4())

    # UPSERT：并发时一个成功 INSERT，另一个走 ON CONFLICT UPDATE
    _db().execute(
        "INSERT INTO history_conversations (id, token, title, messages, msg_count, created_at, updated_at) "
        "VALUES (:id, :token, :title, :messages, :msg_count, :now, :now) "
        "ON CONFLICT (token, title) DO UPDATE SET "
        "messages = EXCLUDED.messages, msg_count = EXCLUDED.msg_count, updated_at = EXCLUDED.updated_at",
        {
            "id": conversation_id,
            "token": token,
            "title": title,
            "messages": messages_json,
            "msg_count": msg_count,
            "now": current,
        },
        commit=True,
    )

    # 查出实际 id（UPDATE 时 id 不变，INSERT 时是新 uuid）
    rows = _db().execute(
        "SELECT id FROM history_conversations WHERE token = :token AND title = :title",
        {"token": token, "title": title},
        commit=False,
        fetch=True,
    )
    actual_id = rows[0][0] if rows else conversation_id

    logger.info(
        "历史记录已保存 | id=%s | title=%s | msg_count=%d",
        actual_id,
        title,
        msg_count,
    )
    return get_history(actual_id, token)


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


def delete_history(conversation_id: str, token: str) -> bool:
    """删除单条历史记录。返回是否实际删除（False = 不存在或无权限）。"""
    rows = _db().execute(
        "DELETE FROM history_conversations WHERE id = :id AND token = :token",
        {"id": conversation_id, "token": token},
        commit=True,
    )
    # DELETE 不返回行数，再查一次确认
    check = _db().execute(
        "SELECT 1 FROM history_conversations WHERE id = :id AND token = :token",
        {"id": conversation_id, "token": token},
        commit=False,
        fetch=True,
    )
    deleted = not bool(check)
    if deleted:
        logger.info("历史记录已删除 | id=%s", conversation_id)
    return deleted
