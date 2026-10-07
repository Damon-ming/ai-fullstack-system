# app-server/src/com/damon/ming/chat/sse/messages.py
"""
SSE 业务消息工厂 —— 统一构造 StreamMessage 并序列化。

职责单一：只管把业务数据打包成 JSON 字符串，不涉及 SSE 协议格式。
事件类型（start/delta/done/error）由外层 SSE event: 字段决定，不嵌入 JSON。

调用方拿到返回值后交给 SseEmitter.emit() 拼成完整的 SSE 行。
"""

import json
import time
import uuid

from src.com.damon.ming.ai.schemas.response import (
    BaseLLMFailedData,
    ChatDeltaData,
    ChatDoneData,
    ChatStartData,
    StreamMessage,
)


class SseMessageFactory:
    """统一构造 StreamMessage 并序列化为 JSON 字符串"""

    @staticmethod
    def get_start_data(llm_model_name: str) -> ChatStartData:
        """构造 start 事件的元数据"""
        return ChatStartData(
            msgId=f"msg_{uuid.uuid4().hex[:12]}",
            conversationId=f"conv_{uuid.uuid4().hex[:8]}",
            model=llm_model_name,
            createdAt=int(time.time()),
            traceId=f"trace_{uuid.uuid4().hex[:16]}",
        )

    @staticmethod
    def start(data: ChatStartData) -> str:
        """构造 start 事件消息 —— 携带本次回答的元信息"""
        msg = StreamMessage[ChatStartData](
            code=100000,
            data=data,
        )
        return json.dumps(msg.model_dump(mode="json"), ensure_ascii=False)

    @staticmethod
    def delta(data: ChatDeltaData) -> str:
        """构造 delta 事件消息 —— 增量分片"""
        msg = StreamMessage[ChatDeltaData](
            code=100000,
            data=data,
        )
        return json.dumps(msg.model_dump(mode="json"), ensure_ascii=False)

    @staticmethod
    def done() -> str:
        """构造 done 事件消息 —— 流结束"""
        msg = StreamMessage[ChatDoneData](
            code=100000,
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
