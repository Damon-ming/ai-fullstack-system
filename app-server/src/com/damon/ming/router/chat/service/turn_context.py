# app-server/src/com/damon/ming/router/chat/service/turn_context.py
"""
一轮对话的请求级上下文 —— 同步 /send/v1 与流式 /chat/v1 共用。

把「请求上下文 + 会话/轮次 id + 提问时刻 + 落库记录器」的构造收敛到一处，
两个端点不再各自重复这段准备逻辑。
"""

import uuid
from dataclasses import dataclass

from fastapi import Request
from src.com.damon.ming.router.chat.sse import SseMessageFactory
from src.com.damon.ming.router.history.service.chat_turn import ChatTurnRecorder
from src.com.damon.ming.thread.pool_manager import RequestContext
from src.com.damon.ming.utils.time import now


@dataclass
class ChatTurnContext:
    """一轮对话从请求到落库所需的全部上下文。"""

    #: pool_mgr 请求上下文（含 CancellationToken），由调用方 finally 统一 cleanup
    request_ctx: RequestContext
    conversation_id: str
    turn_id: str
    recorder: ChatTurnRecorder


def _request_token(request: Request) -> str:
    """从请求上下文获取当前用户 token（与 history 模块口径一致）。"""
    return getattr(request.state, "ctx", None) and request.state.ctx.token or ""


def create_turn(request: Request, body) -> ChatTurnContext:
    """构造一轮对话的上下文。

    会话 id 提前确定：拦截轮次也要落库，需要会话归属。
    轮次 id 与 SSE 链路同口径，下发给客户端的同时作为落库主键，
    保证「客户端看到的 turnId」与「DB 里的 turn_id」是同一轮。
    提问时刻在请求到达即采集，作为全部时延指标的起点。
    """
    ctx = request.app.state.pool_mgr.create_request_context()
    conversation_id = body.conversationId or SseMessageFactory.new_conversation_id()
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    query_at = now()

    recorder = ChatTurnRecorder(
        token=_request_token(request),
        turn_id=turn_id,
        conversation_id=conversation_id,
        query=body.query,
        query_at=query_at,
    )

    return ChatTurnContext(
        request_ctx=ctx,
        conversation_id=conversation_id,
        turn_id=turn_id,
        recorder=recorder,
    )
