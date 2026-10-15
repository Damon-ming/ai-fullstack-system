"""
对话历史 业务逻辑层。

职责：
  - 参数校验与转换
  - 调用 store 层执行持久化
  - 组装返回给 router 的数据结构
"""

from src.com.damon.ming.log import pin
from src.com.damon.ming.router.history import history_store
from src.com.damon.ming.router.history.schemas.bean import (
    HistoryDetailData,
    HistoryListItem,
    HistoryMessageItem,
)
from src.com.damon.ming.utils.time import iso_format

logger = pin("history.service")


def _format_row_common(row) -> dict:
    """DB 行中与列表/详情共享的字段提取。"""
    return {
        "id": row.id,
        "title": row.title,
        "msg_count": row.msg_count or 0,
        "created_at": iso_format(row.created_at),
        "updated_at": iso_format(row.updated_at),
    }


def _row_to_list_item(row) -> HistoryListItem:
    """DB 行 → 列表项 schema。"""
    return HistoryListItem(**_format_row_common(row))


def _messages_to_items(messages: list) -> list[HistoryMessageItem]:
    """原始消息 dict 列表 → schema 列表。"""
    items = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        items.append(
            HistoryMessageItem(
                id=str(msg.get("id", "")),
                text=str(msg.get("text", "")),
                role=str(msg.get("role", "user")),
            )
        )
    return items


def _row_to_detail(row) -> HistoryDetailData:
    """DB 行 → 详情 schema（含消息正文）。"""
    return HistoryDetailData(**_format_row_common(row), messages=_messages_to_items(row.messages))


class HistoryService:
    """对话历史业务逻辑。"""

    @staticmethod
    async def list_history(
        token: str,
        page: int,
        page_size: int,
    ) -> dict:
        """分页获取历史记录列表。"""
        items, total = history_store.list_history(token, page, page_size)
        return {
            "items": [_row_to_list_item(r) for r in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def get_history(
        conversation_id: str,
        token: str,
    ) -> HistoryDetailData | None:
        """获取单条历史记录详情。"""
        row = history_store.get_history(conversation_id, token)
        if row is None:
            return None
        return _row_to_detail(row)

    @staticmethod
    async def save_history(
        token: str,
        title: str,
        messages: list[dict],
    ) -> HistoryDetailData:
        """保存/更新对话历史。"""
        # 清洗消息：只保留 {id, text, role} 三个字段，与前端持久化格式一致
        cleaned = [
            {"id": str(m.get("id", "")), "text": str(m.get("text", "")), "role": str(m.get("role", ""))}
            for m in messages
            if isinstance(m, dict)
        ]
        row = history_store.save_history(token, title.strip(), cleaned)
        return _row_to_detail(row)

    @staticmethod
    async def delete_history(
        conversation_id: str,
        token: str,
    ) -> bool:
        """删除单条历史记录。"""
        return history_store.delete_history(conversation_id, token)
