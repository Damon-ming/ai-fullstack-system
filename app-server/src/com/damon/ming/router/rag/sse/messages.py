# app-server/src/com/damon/ming/chat/sse/messages.py
"""
SSE 业务消息工厂 —— 统一构造 StreamMessage 并序列化。

职责单一：只管把业务数据打包成 JSON 字符串，不涉及 SSE 协议格式。
事件类型（start/delta/done/error）由外层 SSE event: 字段决定，不嵌入 JSON。

调用方拿到返回值后交给 SseEmitter.emit() 拼成完整的 SSE 行。
"""

import json
from datetime import datetime

from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.router.rag.schemas.response import (
    BaseLLMFailedData,
    ChatDeltaData,
    ChatDoneData,
    ChatStartData,
    StreamMessage,
)
from src.com.damon.ming.utils.time import to_unix_timestamp


class SseMessageFactory:
    """统一构造 StreamMessage 并序列化为 JSON 字符串"""

    @staticmethod
    def start(
        turn_id: str,
        conversation_id: str,
        query_at: datetime,
    ) -> str:
        """构造并序列化 start 事件，使用与历史记录一致的 ID 和提问时间。

        turn_id 由调用方生成，与落库后的 history_turns.turn_id 保持一致；
        conversation_id 由调用方解析：新建会话时生成，已有会话时沿用客户端回传的 id；
        query_at 由调用方传入落库用的同一时刻，保证 start 事件与 DB 的
        query_at 完全一致（而不是在发事件时重新取当前时间）。
        """
        data = ChatStartData(
            turnId=turn_id,
            conversationId=conversation_id,
            queryAt=to_unix_timestamp(query_at),
        )
        msg = StreamMessage[ChatStartData](
            code=ErrorCode.OK,
            data=data,
        )
        return json.dumps(msg.model_dump(mode="json"), ensure_ascii=False)

    @staticmethod
    def delta(data: ChatDeltaData) -> str:
        """构造 delta 事件消息 —— 增量分片"""
        msg = StreamMessage[ChatDeltaData](
            code=ErrorCode.OK,
            data=data,
        )
        return json.dumps(msg.model_dump(mode="json"), ensure_ascii=False)

    @staticmethod
    def done(answered_at: datetime) -> str:
        """构造 done 事件消息，并携带与落库一致的回答完成时间。"""
        msg = StreamMessage[ChatDoneData](
            code=ErrorCode.OK,
            data=ChatDoneData(answeredAt=to_unix_timestamp(answered_at)),
        )
        return json.dumps(msg.model_dump(mode="json"), ensure_ascii=False)

    @staticmethod
    def error(biz_code: int, data: BaseLLMFailedData) -> str:
        """构造 error 事件消息 —— 业务 / 系统异常"""
        msg = StreamMessage[BaseLLMFailedData](
            code=biz_code,
            data=data,
        )
        return json.dumps(msg.model_dump(mode="json"), ensure_ascii=False)
