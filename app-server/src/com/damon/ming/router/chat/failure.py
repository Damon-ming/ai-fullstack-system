# app-server/src/com/damon/ming/router/chat/failure.py
"""
chat 链路统一失败响应构造。

同步返回体（BaseLLMFailedResponse）与 SSE error 事件共用一套错误码口径，
把原先散落在 chat_router / preflight 各处的 BaseLLMFailedData 组装收敛到一处。
"""

from src.com.damon.ming.ai.schemas.response import (
    BaseLLMFailedData,
    BaseLLMFailedResponse,
)
from src.com.damon.ming.router.chat.sse import SseMessageFactory


def chat_failure(code: int, msg: str) -> BaseLLMFailedResponse[BaseLLMFailedData]:
    """构造 chat 链路的统一失败响应（同步返回体）。"""
    return BaseLLMFailedResponse[BaseLLMFailedData](
        code=code,
        data=BaseLLMFailedData(error_msg=msg),
    )


def chat_error_event(code: int, msg: str) -> str:
    """构造 SSE error 事件的消息体（已序列化 JSON，交给 SseEmitter.emit）。"""
    return SseMessageFactory.error(code, BaseLLMFailedData(error_msg=msg))
