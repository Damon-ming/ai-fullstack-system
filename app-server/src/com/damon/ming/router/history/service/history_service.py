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
from src.com.damon.ming.router.history.schemas.bean import (
    HistoryDetailData,
    HistoryListItem,
    HistoryTurnInput,
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
        createdAt=iso_format(row.created_at),
        updatedAt=iso_format(row.updated_at),
    )


def _detail_to_data(row) -> HistoryDetailData:
    """详情行（会话 + 轮次）→ 详情 schema。"""
    conv = row.conversation
    return HistoryDetailData(
        conversationId=conv.id,
        title=conv.title,
        createdAt=iso_format(conv.created_at),
        updatedAt=iso_format(conv.updated_at),
        turns=[_turn_to_item(t) for t in row.turns],
    )


class HistoryService:
    """对话历史业务逻辑。"""

    @staticmethod
    def list_history(
        token: str,
        page: int,
        page_size: int,
    ) -> list[HistoryListItem]:
        """分页获取会话列表（不含轮次正文）。"""
        rows, _total = history_store.list_history(token, page, page_size)
        return [_conv_to_list_item(r) for r in rows]

    @staticmethod
    def get_history(
        conversation_id: str,
        token: str,
    ) -> HistoryDetailData | None:
        """获取单个会话详情（含全部轮次）。"""
        row = history_store.get_history(conversation_id, token)
        return _detail_to_data(row) if row else None

    @staticmethod
    def save_history(
        token: str,
        title: str,
        conversation_id: str | None,
        turns: list[HistoryTurnInput],
    ) -> HistoryDetailData | None:
        """保存会话（客户端口径）：按 conversation_id 幂等 upsert，整体替换轮次。"""
        row = history_store.save_history(
            token=token,
            conversation_id=conversation_id or "",
            title=title.strip(),
            turns=[t.model_dump() for t in turns],
        )
        return _detail_to_data(row) if row else None

    @staticmethod
    def delete_history(
        conversation_id: str,
        token: str,
    ) -> bool:
        """删除会话及其全部轮次。"""
        return history_store.delete_history(conversation_id, token)

    @staticmethod
    def save_turn(
        token: str,
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
        """写入一轮对话（服务端 chat 链路调用）。

        服务端是会话数据的唯一写入方，不依赖客户端回传整段对话。
        turn_id 由调用方生成，与 SSE start 事件下发的 turnId 一致。
        返回实际会话 id；会话不属于当前 token 时为空串。
        """
        return history_store.append_turn(
            token=token,
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
