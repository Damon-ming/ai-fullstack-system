# app-server/src/com/damon/ming/router/history/history_store.py
"""
对话历史 存储层。

职责：
  - 会话（history_conversations）与轮次（history_turns）的 CRUD
  - 按 user_id 隔离，不同用户互不干扰
  - 分页列表查询（不含轮次正文，按 updated_at 倒序）
  - 详情查询（会话 + 轮次列表，按 query_at 升序）
  - 写入（append_turn：轮次纯 INSERT，无读改写竞态）

详情读取与删除均在事务内提交：会话头与轮次同生共死，不出现撕裂视图。
存储：通过共享连接池持久化。
"""

import time
from datetime import datetime
from enum import Enum

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.com.damon.ming.app.tables.account_tables import users
from src.com.damon.ming.app.tables.history_tables import (
    HistoryConversationRow,
    HistoryDetailRow,
    HistoryTurnRow,
    history_conversations,
    history_turns,
)
from src.com.damon.ming.db import get_default_db
from src.com.damon.ming.log import pin
from src.com.damon.ming.utils.cursor_codec import (
    CursorCodecError,
    decode_cursor_payload,
    encode_cursor_payload,
)

logger = pin("history.store")
MAX_PINNED_CONVERSATIONS = 30


class InvalidHistoryCursor(ValueError):
    """历史记录分页游标格式错误。"""


class PinHistoryResult(str, Enum):
    """置顶会话操作结果。"""

    PINNED = "pinned"
    ALREADY_PINNED = "already_pinned"
    LIMIT_REACHED = "limit_reached"
    NOT_FOUND = "not_found"


def _encode_cursor(query_at: datetime, turn_id: str) -> str:
    return encode_cursor_payload(
        {"queryAt": query_at.isoformat(), "turnId": turn_id}
    )


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        value = decode_cursor_payload(cursor)
        query_at = datetime.fromisoformat(value["queryAt"])
        turn_id = value["turnId"]
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError
        return query_at, turn_id
    except (CursorCodecError, ValueError, KeyError, TypeError) as exc:
        raise InvalidHistoryCursor("分页游标无效") from exc


def _encode_list_cursor(updated_at: datetime, conversation_id: str) -> str:
    return encode_cursor_payload(
        {"updatedAt": updated_at.isoformat(), "conversationId": conversation_id}
    )


def _decode_list_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        value = decode_cursor_payload(cursor)
        updated_at = datetime.fromisoformat(value["updatedAt"])
        conversation_id = value["conversationId"]
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError
        return updated_at, conversation_id
    except (CursorCodecError, ValueError, KeyError, TypeError) as exc:
        raise InvalidHistoryCursor("分页游标无效") from exc


def _db():
    return get_default_db()


def _run_transaction(operation, *, description: str):
    """在事务内执行 operation(conn)，失败按 retry_count 重试。

    transaction() 本身不带重试（与 execute() 不同），这里补齐，
    避免瞬时连接故障让一次读 / 写直接失败。
    operation 正常返回即提交，抛异常则回滚。
    """
    db = _db()
    attempts = max(db.retry_count, 1)
    backoff = db.backoff_seconds
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            with db.transaction() as conn:
                return operation(conn)
        except Exception as e:
            last_error = e
            logger.warning(
                "%s 失败（尝试 %d/%d）| error=%s",
                description,
                attempt + 1,
                attempts,
                e,
            )
            if attempt + 1 < attempts:
                time.sleep(backoff * (attempt + 1))

    logger.error(
        "%s 最终失败（已重试 %d 次）| error=%s", description, attempts, last_error
    )
    raise last_error


# ---------------------------------------------------------------------------
# 列表 & 分页
# ---------------------------------------------------------------------------


def list_history(
    user_id: int,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[
    list[HistoryConversationRow], list[HistoryConversationRow], bool, str | None
]:
    """置顶会话全部返回；普通会话按 updated_at/id 倒序游标分页。"""
    cursor_values = _decode_list_cursor(cursor) if cursor else None
    base = select(history_conversations).where(
        history_conversations.c.user_id == user_id
    )
    pinned_rows = _db().execute(
        base.where(history_conversations.c.is_pinned.is_(True))
        .order_by(
            history_conversations.c.updated_at.desc(),
            history_conversations.c.id.desc(),
        )
        .limit(MAX_PINNED_CONVERSATIONS),
        commit=False,
        fetch=True,
    )
    query = base.where(history_conversations.c.is_pinned.is_(False))
    if cursor_values:
        cursor_at, cursor_id = cursor_values
        query = query.where(
            or_(
                history_conversations.c.updated_at < cursor_at,
                and_(
                    history_conversations.c.updated_at == cursor_at,
                    history_conversations.c.id < cursor_id,
                ),
            )
        )
    rows = _db().execute(
        query.order_by(
            history_conversations.c.updated_at.desc(),
            history_conversations.c.id.desc(),
        ).limit(limit + 1),
        commit=False,
        fetch=True,
    )
    has_more = len(rows or []) > limit
    rows = (rows or [])[:limit]

    def _to_rows(values, is_pinned: bool) -> list[HistoryConversationRow]:
        return [
            HistoryConversationRow(
                id=r[0],
                user_id=r[1],
                title=r[2],
                is_pinned=is_pinned,
                created_at=r[4],
                updated_at=r[5],
            )
            for r in values
        ]

    pinned_items = _to_rows(pinned_rows or [], True)
    items = _to_rows(rows, False)
    next_cursor = (
        _encode_list_cursor(items[-1].updated_at, items[-1].id)
        if has_more and items
        else None
    )
    return pinned_items, items, has_more, next_cursor


# ---------------------------------------------------------------------------
# 详情
# ---------------------------------------------------------------------------


def get_history(
    conversation_id: str,
    user_id: int,
    limit: int = 50,
    cursor: str | None = None,
) -> HistoryDetailRow | None:
    """查询单个会话详情的一页轮次，按提问时间升序。

    会话头与轮次在同一事务内读取：中途不会被并发删除 / 写入插队，
    避免出现「会话已删、轮次还在」或反之的撕裂视图。
    """

    cursor_values = _decode_cursor(cursor) if cursor else None

    def _read(conn) -> HistoryDetailRow | None:
        c = conn.execute(
            select(history_conversations).where(
                history_conversations.c.id == conversation_id,
                history_conversations.c.user_id == user_id,
            )
        ).fetchone()
        if c is None:
            return None
        conversation = HistoryConversationRow(
            id=c[0],
            user_id=c[1],
            title=c[2],
            is_pinned=c[3],
            created_at=c[4],
            updated_at=c[5],
        )

        turn_query = select(history_turns).where(
            history_turns.c.conversation_id == conversation_id
        )
        if cursor_values:
            cursor_at, cursor_turn_id = cursor_values
            turn_query = turn_query.where(
                or_(
                    history_turns.c.query_at > cursor_at,
                    and_(
                        history_turns.c.query_at == cursor_at,
                        history_turns.c.turn_id > cursor_turn_id,
                    ),
                )
            )
        page_rows = conn.execute(
            turn_query.order_by(
                history_turns.c.query_at.asc(), history_turns.c.turn_id.asc()
            ).limit(limit + 1)
        ).fetchall()
        has_more = len(page_rows) > limit
        turn_rows = page_rows[:limit]
        turns = [
            HistoryTurnRow(
                turn_id=r[0],
                conversation_id=r[1],
                query=r[2],
                reasoning=r[3],
                content=r[4],
                error_msg=r[5],
                query_at=r[6],
                first_token_at=r[7],
                reasoning_done_at=r[8],
                answered_at=r[9],
            )
            for r in (turn_rows or [])
        ]
        next_cursor = (
            _encode_cursor(turn_rows[-1][6], turn_rows[-1][0])
            if has_more and turn_rows
            else None
        )
        return HistoryDetailRow(
            conversation=conversation,
            turns=turns,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    return _run_transaction(_read, description=f"历史详情读取 | id={conversation_id}")


# ---------------------------------------------------------------------------
# 写入：append_turn
# ---------------------------------------------------------------------------


def append_turn(
    user_id: int,
    turn_id: str,
    conversation_id: str,
    title: str,
    query: str,
    reasoning: str | None,
    content: str,
    query_at: datetime,
    first_token_at: datetime | None,
    reasoning_done_at: datetime | None,
    answered_at: datetime,
    error_msg: str | None = None,
) -> str:
    """写入一轮问答，返回会话 id（写入被拒绝时返回空串）。

    本模块是会话数据的唯一写入方：
      - 会话不存在 → 按 conversation_id 新建
      - 会话已存在 → 仅刷新 updated_at
    会话必须属于当前 user_id，否则整轮写入被拒绝。

    turn_id 由调用方生成，需全局唯一。

    轮次为纯 INSERT，不像旧的「读出 messages → 拼接 → 写回」那样存在
    并发覆盖竞态。

    会话 upsert 与轮次插入在同一事务内提交：任一步失败则整体回滚，
    避免留下「有会话、无轮次」的空壳行。

    事务体重试 retry_count 次（与 execute() 同口径）：瞬时连接故障不应
    让一轮已完成的回答丢失。turn_id 在重试外生成、轮次插入带
    ON CONFLICT DO NOTHING，保证重试幂等 —— 即使上一次提交实际已生效
    只是应答丢了，重试也不会插进重复轮次。
    """
    db = _db()
    retry = db.retry_count
    backoff = db.backoff_seconds
    last_error: Exception | None = None

    for attempt in range(max(retry, 1)):
        try:
            with db.transaction() as conn:
                statement = pg_insert(history_conversations).values(
                    id=conversation_id,
                    user_id=user_id,
                    title=title,
                    created_at=answered_at,
                    updated_at=answered_at,
                )
                rows = conn.execute(
                    statement.on_conflict_do_update(
                        index_elements=[history_conversations.c.id],
                        set_={
                            history_conversations.c.updated_at: statement.excluded.updated_at
                        },
                        where=history_conversations.c.user_id
                        == statement.excluded.user_id,
                    ).returning(history_conversations.c.id)
                ).fetchall()
                if not rows:
                    logger.warning(
                        "会话不存在或不属于当前用户，已跳过轮次写入 | id=%s",
                        conversation_id,
                    )
                    return ""

                conn.execute(
                    pg_insert(history_turns)
                    .values(
                        turn_id=turn_id,
                        conversation_id=conversation_id,
                        query=query,
                        reasoning=reasoning or None,
                        content=content,
                        error_msg=error_msg or None,
                        query_at=query_at,
                        first_token_at=first_token_at,
                        reasoning_done_at=reasoning_done_at,
                        answered_at=answered_at,
                    )
                    .on_conflict_do_nothing(index_elements=[history_turns.c.turn_id])
                )
            logger.info(
                "轮次已写入 | conversation_id=%s | turn_id=%s | reasoning=%s",
                conversation_id,
                turn_id,
                "yes" if reasoning else "no",
            )
            return conversation_id
        except Exception as e:
            last_error = e
            logger.warning(
                "轮次写入失败（尝试 %d/%d）| id=%s | error=%s",
                attempt + 1,
                retry,
                conversation_id,
                e,
            )
            if attempt + 1 < retry:
                time.sleep(backoff * (attempt + 1))

    logger.error(
        "轮次写入最终失败（已重试 %d 次）| id=%s | error=%s",
        retry,
        conversation_id,
        last_error,
    )
    raise last_error


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


def delete_history(conversation_id: str, user_id: int) -> bool:
    """删除会话及其全部轮次。返回是否实际删除（False = 不存在或无权限）。

    存在性校验与两条 DELETE 在同一事务内提交：要么全删，要么全不删，
    不会出现「轮次已删、会话还在」的中间态。
    """

    def _delete(conn) -> bool:
        rows = conn.execute(
            select(history_conversations.c.id).where(
                history_conversations.c.id == conversation_id,
                history_conversations.c.user_id == user_id,
            )
        ).fetchall()
        if not rows:
            return False

        # turns 与 conversations 之间是逻辑外键，需显式级联
        conn.execute(
            history_turns.delete().where(
                history_turns.c.conversation_id == conversation_id
            )
        )
        conn.execute(
            history_conversations.delete().where(
                history_conversations.c.id == conversation_id,
                history_conversations.c.user_id == user_id,
            )
        )
        return True

    deleted = _run_transaction(
        _delete, description=f"历史会话删除 | id={conversation_id}"
    )
    if deleted:
        logger.info("历史会话已删除 | id=%s", conversation_id)
    return deleted


def pin_history(conversation_id: str, user_id: int) -> PinHistoryResult:
    """置顶一个会话并返回操作结果。"""

    def _pin(conn) -> PinHistoryResult:
        # 同一用户的置顶操作串行化，确保并发请求也不会突破上限。
        conn.execute(
            select(users.c.user_id).where(users.c.user_id == user_id).with_for_update()
        ).fetchone()
        row = conn.execute(
            select(history_conversations.c.is_pinned)
            .where(
                history_conversations.c.id == conversation_id,
                history_conversations.c.user_id == user_id,
            )
            .with_for_update()
        ).fetchone()
        if row is None:
            return PinHistoryResult.NOT_FOUND
        if row[0]:
            return PinHistoryResult.ALREADY_PINNED

        pinned_count = conn.execute(
            select(func.count())
            .select_from(history_conversations)
            .where(
                history_conversations.c.user_id == user_id,
                history_conversations.c.is_pinned.is_(True),
            )
        ).scalar_one()
        if pinned_count >= MAX_PINNED_CONVERSATIONS:
            return PinHistoryResult.LIMIT_REACHED

        conn.execute(
            history_conversations.update()
            .where(history_conversations.c.id == conversation_id)
            .values(is_pinned=True)
        )
        return PinHistoryResult.PINNED

    return _run_transaction(_pin, description=f"会话置顶 | id={conversation_id}")
