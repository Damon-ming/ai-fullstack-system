# app-server/src/com/damon/ming/chat/sse/messages.py
"""
SSE 业务消息工厂 —— 统一构造 StreamMessage 并序列化。

职责单一：只管把业务数据打包成 JSON 字符串，不涉及 SSE 协议格式。
事件类型（start/delta/done/error）由外层 SSE event: 字段决定，不嵌入 JSON。

调用方拿到返回值后交给 SseEmitter.emit() 拼成完整的 SSE 行。
"""

import json
import uuid

from src.com.damon.ming.ai.schemas.response import (
    BaseLLMFailedData,
    ChatDeltaData,
    ChatDoneData,
    ChatStartData,
    StreamMessage,
)
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.utils.time import unix_timestamp


class SseMessageFactory:
    """统一构造 StreamMessage 并序列化为 JSON 字符串"""

    @staticmethod
    def new_conversation_id() -> str:
        """生成新的会话 id。

        该 id 同时作为 history_conversations 表主键，跨轮次稳定，
        由 start 事件下发，客户端后续轮次原样回传。
        """
        return f"conv_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def get_start_data(
        llm_model_name: str,
        conversation_id: str | None = None,
    ) -> ChatStartData:
        """构造 start 事件的元数据。

        conversation_id 由调用方解析：新建会话时由 new_conversation_id() 生成，
        已有会话时沿用客户端回传的 id，保证一个会话内多轮共享同一 id。
        """
        return ChatStartData(
            msgId=f"msg_{uuid.uuid4().hex[:12]}",
            conversationId=conversation_id or SseMessageFactory.new_conversation_id(),
            model=llm_model_name,
            createdAt=unix_timestamp(),
            traceId=f"trace_{uuid.uuid4().hex[:16]}",
        )

    @staticmethod
    def start(data: ChatStartData) -> str:
        """构造 start 事件消息 —— 携带本次回答的元信息"""
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
    def done() -> str:
        """构造 done 事件消息 —— 流结束"""
        msg = StreamMessage[ChatDoneData](
            code=ErrorCode.OK,
            data=ChatDoneData(),
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
