# app-server/src/com/damon/ming/router/history/service/history_service.py
"""
对话历史 业务逻辑层。

职责：
  - 参数校验与转换
  - 调用 store 层执行持久化
  - 组装返回给 router 的数据结构
"""

from datetime import datetime

from src.com.damon.ming.log import pin
from src.com.damon.ming.router.history import history_store
from src.com.damon.ming.router.history.history_store import PinHistoryResult
from src.com.damon.ming.router.history.schemas.bean import (
    HistoryDetailData,
    HistoryListData,
    HistoryListItem,
    HistoryTurnItem,
)
from src.com.damon.ming.utils.time import iso_format

logger = pin("history.service")


def _turn_to_item(row) -> HistoryTurnItem:
    """DB 行 → 轮次 schema。"""
    return HistoryTurnItem(
        turnId=row.turn_id,
        query=row.query,
        reasoning=row.reasoning or "",
        content=row.content,
        errorMsg=row.error_msg or "",
        queryAt=iso_format(row.query_at),
        firstTokenAt=iso_format(row.first_token_at),
        reasoningDoneAt=iso_format(row.reasoning_done_at),
        answeredAt=iso_format(row.answered_at),
    )


def _conv_to_list_item(row) -> HistoryListItem:
    """DB 行 → 会话列表项 schema。"""
    return HistoryListItem(
        conversationId=row.id,
        title=row.title,
        isPinned=row.is_pinned,
        createdAt=iso_format(row.created_at),
        updatedAt=iso_format(row.updated_at),
    )


def _detail_to_data(row) -> HistoryDetailData:
    """详情行（会话 + 轮次）→ 详情 schema。"""
    conv = row.conversation
    return HistoryDetailData(
        conversationId=conv.id,
        title=conv.title,
        isPinned=conv.is_pinned,
        createdAt=iso_format(conv.created_at),
        updatedAt=iso_format(conv.updated_at),
        turns=[_turn_to_item(t) for t in row.turns],
        hasMore=row.has_more,
        nextCursor=row.next_cursor,
    )


class HistoryService:
    """对话历史业务逻辑。"""

    @staticmethod
    def list_history(
        user_id: int,
        limit: int,
        cursor: str | None = None,
    ) -> HistoryListData:
        """游标分页获取会话列表（不含轮次正文）。"""
        pinned_rows, rows, has_more, next_cursor = history_store.list_history(
            user_id, limit, cursor
        )
        return HistoryListData(
            pinned=[_conv_to_list_item(row) for row in pinned_rows],
            items=[_conv_to_list_item(row) for row in rows],
            hasMore=has_more,
            nextCursor=next_cursor,
        )

    @staticmethod
    def search_history(
        user_id: int, keyword: str, limit: int = 20
    ) -> list[HistoryListItem]:
        rows = history_store.search_history(user_id, keyword, limit)
        return [_conv_to_list_item(row) for row in rows]

    @staticmethod
    def get_history(
        conversation_id: str,
        user_id: int,
        limit: int,
        cursor: str | None = None,
    ) -> HistoryDetailData | None:
        """获取单个会话详情的一页轮次。"""
        row = history_store.get_history(conversation_id, user_id, limit, cursor)
        return _detail_to_data(row) if row else None

    @staticmethod
    def delete_history(
        conversation_id: str,
        user_id: int,
    ) -> bool:
        """删除会话及其全部轮次。"""
        return history_store.delete_history(conversation_id, user_id)

    @staticmethod
    def pin_history(conversation_id: str, user_id: int) -> PinHistoryResult:
        """置顶一个会话；每个用户最多 30 个。"""
        return history_store.pin_history(conversation_id, user_id)

    @staticmethod
    def unpin_history(
        conversation_id: str, user_id: int
    ) -> history_store.UnpinHistoryResult:
        """取消置顶一个会话。"""
        return history_store.unpin_history(conversation_id, user_id)

    @staticmethod
    def save_turn(
        user_id: int,
        turn_id: str,
        conversation_id: str,
        title: str,
        query: str,
        reasoning: str,
        content: str,
        query_at: datetime,
        first_token_at: datetime | None,
        reasoning_done_at: datetime | None,
        answered_at: datetime,
        error_msg: str | None = None,
    ) -> str:
        """写入一轮对话。

        本服务是会话数据的唯一写入方，不依赖客户端回传整段对话。
        turn_id 由调用方生成，需全局唯一。
        返回实际会话 id；会话不属于当前 user_id 时为空串。
        """
        return history_store.append_turn(
            user_id=user_id,
            turn_id=turn_id,
            conversation_id=conversation_id,
            title=title.strip(),
            query=query,
            reasoning=reasoning,
            content=content,
            query_at=query_at,
            first_token_at=first_token_at,
            reasoning_done_at=reasoning_done_at,
            answered_at=answered_at,
            error_msg=error_msg,
        )
