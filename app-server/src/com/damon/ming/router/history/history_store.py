"""
对话历史 存储层。

职责：
  - 会话（history_conversations）与轮次（history_turns）的 CRUD
  - 按 token 隔离，不同用户互不干扰
  - 分页列表查询（不含轮次正文，按 updated_at 倒序）
  - 详情查询（会话 + 轮次列表，按 query_at 升序）
  - 写入（append_turn：轮次纯 INSERT，无读改写竞态）

详情读取与删除均在事务内提交：会话头与轮次同生共死，不出现撕裂视图。
存储：通过共享连接池持久化。
"""

import time
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.com.damon.ming.app.tables.history_tables import (
    HistoryConversationRow,
    HistoryDetailRow,
    HistoryTurnRow,
    history_conversations,
    history_turns,
)
from src.com.damon.ming.db import get_default_db
from src.com.damon.ming.log import pin

logger = pin("history.store")


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
    token: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[HistoryConversationRow], int]:
    """分页查询会话列表（不含轮次正文），按 updated_at 倒序。

    返回 (items, total)。
    """
    offset = (page - 1) * page_size

    count_rows = _db().execute(
        select(func.count())
        .select_from(history_conversations)
        .where(history_conversations.c.token == token),
        commit=False,
        fetch=True,
    )
    total = count_rows[0][0] if count_rows else 0

    rows = _db().execute(
        select(history_conversations)
        .where(history_conversations.c.token == token)
        .order_by(history_conversations.c.updated_at.desc())
        .limit(page_size)
        .offset(offset),
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
    """查询单个会话详情（含全部轮次，按提问时间升序）。

    会话头与轮次在同一事务内读取：中途不会被并发删除 / 写入插队，
    避免出现「会话已删、轮次还在」或反之的撕裂视图。
    """

    def _read(conn) -> HistoryDetailRow | None:
        c = conn.execute(
            select(history_conversations).where(
                history_conversations.c.id == conversation_id,
                history_conversations.c.token == token,
            )
        ).fetchone()
        if c is None:
            return None
        conversation = HistoryConversationRow(
            id=c[0],
            token=c[1],
            title=c[2],
            created_at=c[3],
            updated_at=c[4],
        )

        turn_rows = conn.execute(
            select(history_turns)
            .where(history_turns.c.conversation_id == conversation_id)
            .order_by(history_turns.c.query_at.asc(), history_turns.c.turn_id.asc())
        ).fetchall()
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
        return HistoryDetailRow(conversation=conversation, turns=turns)

    return _run_transaction(_read, description=f"历史详情读取 | id={conversation_id}")


# ---------------------------------------------------------------------------
# 写入：append_turn
# ---------------------------------------------------------------------------


def append_turn(
    token: str,
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
    会话必须属于当前 token，否则整轮写入被拒绝。

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
                    token=token,
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
                        where=history_conversations.c.token == statement.excluded.token,
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


def delete_history(conversation_id: str, token: str) -> bool:
    """删除会话及其全部轮次。返回是否实际删除（False = 不存在或无权限）。

    存在性校验与两条 DELETE 在同一事务内提交：要么全删，要么全不删，
    不会出现「轮次已删、会话还在」的中间态。
    """

    def _delete(conn) -> bool:
        rows = conn.execute(
            select(history_conversations.c.id).where(
                history_conversations.c.id == conversation_id,
                history_conversations.c.token == token,
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
                history_conversations.c.token == token,
            )
        )
        return True

    deleted = _run_transaction(
        _delete, description=f"历史会话删除 | id={conversation_id}"
    )
    if deleted:
        logger.info("历史会话已删除 | id=%s", conversation_id)
    return deleted
