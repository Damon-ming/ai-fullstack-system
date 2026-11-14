# app-server/src/com/damon/ming/router/chat/chat_router.py
"""
chat 链路两个端点 —— 每个端点自包含完整编排。

一轮对话的执行顺序（同步 /send/v1 与流式 /chat/v1 一致）：
    构造本轮上下文 → Phase 0 输入校验 → Phase 1 护栏 → Phase 2 RAG+推理
    → 成功收尾落库 → 返回 / 发 done 事件
任一环节失败：set_error → 返回失败响应 / 发 error 事件
finally：清理请求上下文 + 未落库则兜底落库

只把「跨端点复用的业务能力」抽到外部，编排本身留在本文件：
  - preflight.py:   Phase 0/1 的检查能力（各 2 个调用点）
  - chat_core.py:   Phase 2 的 RAG+推理流程（2 个调用点，原先两份重复实现）
  - failure.py:     失败响应 / SSE error 事件构造（preflight 也要用）
  - service/chat_turn.py: 本轮内容的累积与落库（chat 自己的业务，字段对应 history_turns 表）
"""

import asyncio
import uuid

from fastapi import APIRouter, Request
from src.com.damon.ming.ai.inference.base_inference import STREAM_TYPE_REASONING
from src.com.damon.ming.ai.schemas.response import (
    BaseLLMSuccessData,
    BaseLLMSuccessResponse,
    ChatDeltaData,
)
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.exception.server_error import get_safe_error_message
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.chat.failure import chat_error_event, chat_failure
from src.com.damon.ming.router.chat.preflight import (
    check_guardrail_with_timeout,
    check_input,
)
from src.com.damon.ming.router.chat.schemas.bean import ChatRequest
from src.com.damon.ming.router.chat.service.chat_core import generate_answer
from src.com.damon.ming.router.chat.service.chat_turn import ChatTurnRecorder
from src.com.damon.ming.router.chat.sse import SseEmitter, SseMessageFactory
from src.com.damon.ming.thread.pool_manager import RequestScope
from src.com.damon.ming.utils.time import now
from sse_starlette.sse import EventSourceResponse

logger = pin("chat.router")

router = APIRouter(prefix="/api/llm", tags=["聊天模块"])


def _request_token(request: Request) -> str:
    """从请求上下文获取当前用户 token（与 history 模块口径一致）。"""
    client = getattr(request.state, "client", None)
    return (client.token if client else "") or ""


def _create_recorder(request: Request, body) -> ChatTurnRecorder:
    """创建本轮对话的落库记录器（turn_id 自动生成，调用方无需传参）。

    conversation_id 由前端指定或新建：拦截轮次也要落库，需要会话归属。
    提问时刻在请求到达即采集，作为全部时延指标的起点。
    """
    return ChatTurnRecorder(
        token=_request_token(request),
        turn_id=f"turn_{uuid.uuid4().hex[:12]}",
        conversation_id=body.conversationId or SseMessageFactory.new_conversation_id(),
        query=body.query,
        query_at=now(),
        db_executor=request.app.state.ai.pool_mgr.get_pool("database_query"),
    )


def _blocked_message(blocked, fallback: str) -> str:
    """取拦截文案：优先响应体里的，缺失时用调用方给的本地化兜底。"""
    return blocked.data.error_msg if blocked.data else fallback


@router.post("/send/v1")
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest):
    """同步问答 —— 走流式通道缓冲拼接，一次性返回完整回答。"""
    logger.info(
        "同步聊天请求开始 | query_length=%s | reason=%s",
        len(body.query),
        body.reason,
    )

    # ── 本轮对话的上下文 ─────────────────────────────────────────────
    # 请求作用域（含 CancellationToken，finally 统一 cleanup）
    scope = request.app.state.ai.pool_mgr.create_request_scope()
    # 落库记录器：turn_id 由工厂自动生成，conversation_id 供响应回传
    recorder = _create_recorder(request, body)

    try:
        # ── Phase 0: 前置输入校验（纯本地规则，零 IO，拦截无效/攻击输入） ──
        input_blocked = check_input(body.query)
        if input_blocked is not None:
            # 拦截文案是用户实际看到的一轮回答，入库为正文（不是 error_msg）
            recorder.add_content(_blocked_message(input_blocked, ""))
            await recorder.persist()
            # 回传会话 id：拦截轮次已落库，客户端后续轮次应追加到同一会话
            return chat_failure(
                input_blocked.code,
                _blocked_message(input_blocked, ""),
                recorder.conversation_id,
            )

        # ── Phase 1: 护栏检测（独立超时，超时 fail-open 放行） ──
        blocked = await check_guardrail_with_timeout(request.app.state, body.query)
        if blocked is not None:
            recorder.add_content(_blocked_message(blocked, ""))
            await recorder.persist()
            return chat_failure(
                blocked.code,
                _blocked_message(blocked, ""),
                recorder.conversation_id,
            )

        # ── Phase 2: RAG + 推理（超时预算覆盖整段，见 generate_answer） ──
        async for token in generate_answer(
            request.app.state, body.query, body.reason, scope.cancellation_token
        ):
            recorder.record_token(token.type, token.content, now())

        # ── 成功收尾：标记回答完成并落库（服务端写入，不依赖客户端回传） ──
        recorder.mark_answered(now())
        persist_ok = await recorder.persist()
        # 报「保存失败」之前先兜底重试一次，避免瞬时故障误报
        if not persist_ok:
            persist_ok = await recorder.ensure_persisted()

        # 同步链路没有流式缓冲可展示，落库失败只能整体报错
        if not persist_ok:
            return chat_failure(
                ErrorCode.CHAT.PERSIST_FAILED,
                t(I18nKey.CHAT_PERSIST_FAILED),
                recorder.conversation_id,
            )

        logger.info("同步聊天请求完成")

        # 外层统一返回：conversationId 必须回传，客户端才能把后续轮次追加到同一会话。
        # reasoning 与流式链路同口径：模型未进思考模式时为空串。
        return BaseLLMSuccessResponse[BaseLLMSuccessData](
            code=ErrorCode.OK,
            data=BaseLLMSuccessData(
                data={
                    "content": recorder.content,
                    "reasoning": recorder.reasoning,
                    "conversationId": recorder.conversation_id,
                }
            ),
        )
    except TimeoutError:
        timeout_msg = t(I18nKey.CHAT_TIMEOUT)
        recorder.set_error(timeout_msg)
        logger.warning("同步聊天请求超时")
        return chat_failure(
            ErrorCode.CHAT.TIMEOUT, timeout_msg, recorder.conversation_id
        )
    except asyncio.CancelledError:
        # 主动取消：不展示客户端文案，但已交付内容仍要落库
        logger.warning("【统计】同步聊天请求被客户端主动取消")
        raise
    except Exception as e:
        err_msg = get_safe_error_message(e)
        recorder.set_error(err_msg)
        logger.exception("同步聊天请求未知异常")
        return chat_failure(ErrorCode.CHAT.UNKNOWN, err_msg, recorder.conversation_id)
    finally:
        # 请求结束（无论成功/失败/取消）：清理请求上下文，回收线程资源
        scope.cleanup()
        # 失败 / 中断路径兜底落库：DB 存「服务端已交付的内容」。
        # 成功路径已落库则跳过；未尝试或上次失败则再给一次机会
        await recorder.ensure_persisted()


@router.post("/chat/v1")
@limiter.limit("10/minute")
async def chat_stream(request: Request, body: ChatRequest):
    """流式问答接口，SSE流式输出（W3C EventSource 标准格式）"""
    logger.info("流式聊天请求开始 | query_length=%s", len(body.query))

    # 本轮对话的上下文：请求作用域 + 落库记录器（turn_id 由工厂自动生成）
    scope = request.app.state.ai.pool_mgr.create_request_scope()
    recorder = _create_recorder(request, body)

    return EventSourceResponse(
        stream_chat_generator(request, body, scope, recorder),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


async def stream_chat_generator(
    request: Request,
    body: ChatRequest,
    scope: RequestScope,
    recorder: ChatTurnRecorder,
):
    """流式问答 SSE 生成器 —— 编排与同步端点一致，只是交付方式不同。

    recorder 由外部工厂创建（turn_id 自动生成），本函数只负责编排与交付。
    """
    emitter = SseEmitter(retry_ms=request.app.state.chat.retry_ms)
    turn_id = recorder.turn_id
    conversation_id = recorder.conversation_id

    try:
        # ── start 事件：在信号量外立即发送，客户端无需排队等待即可感知连接建立 ──
        yield emitter.emit(
            "start",
            SseMessageFactory.start(
                SseMessageFactory.get_start_data(
                    turn_id, conversation_id, recorder.query_at
                )
            ),
            retry=True,
        )

        # ── Phase 0: 前置输入校验（纯本地规则，零 IO，拦截无效/攻击输入） ──
        input_blocked = check_input(body.query)
        if input_blocked is not None:
            # 拦截文案走正常 delta/done 通道，保证刷新后聊天室与历史一致
            msg = _blocked_message(input_blocked, t(I18nKey.VALIDATOR_EMPTY_INPUT))
            recorder.add_content(msg)
            await recorder.persist()
            yield emitter.emit(
                "delta",
                SseMessageFactory.delta(ChatDeltaData(content=msg)),
            )
            yield emitter.emit("done", SseMessageFactory.done())
            return

        # ── Phase 1: 护栏检测（独立超时，超时 fail-open 放行） ──
        blocked_resp = await check_guardrail_with_timeout(request.app.state, body.query)
        if blocked_resp is not None:
            msg = _blocked_message(blocked_resp, t(I18nKey.GUARDRAIL_BLOCKED))
            recorder.add_content(msg)
            await recorder.persist()
            yield emitter.emit(
                "delta",
                SseMessageFactory.delta(ChatDeltaData(content=msg)),
            )
            yield emitter.emit("done", SseMessageFactory.done())
            return

        # ── Phase 2: RAG + 推理（超时预算覆盖整段，见 generate_answer） ──
        async for token in generate_answer(
            request.app.state, body.query, body.reason, scope.cancellation_token
        ):
            # 根据 token 类型发射不同事件：
            #   reasoning → event: "reasoning"（推理过程）
            #   content   → event: "delta"（正文回答）
            recorder.record_token(token.type, token.content, now())
            event_name = "reasoning" if token.type == STREAM_TYPE_REASONING else "delta"
            yield emitter.emit(
                event_name,
                SseMessageFactory.delta(ChatDeltaData(content=token.content)),
            )

        # ── 成功收尾：标记回答完成并落库（服务端写入，不依赖客户端回传） ──
        recorder.mark_answered(now())
        persist_ok = await recorder.persist()
        # 发「保存失败」事件之前先兜底重试一次，避免瞬时故障误报
        if not persist_ok:
            persist_ok = await recorder.ensure_persisted()

        # 回答已完整交付，但历史没写进去：用专属错误码区分「模型失败」
        # 与「存不下」，避免客户端把已显示的回答当成模型没答上
        if not persist_ok:
            yield emitter.emit(
                "error",
                chat_error_event(
                    ErrorCode.CHAT.PERSIST_FAILED, t(I18nKey.CHAT_PERSIST_FAILED)
                ),
            )
            return

        # ── done 事件（结束包） ──
        yield emitter.emit("done", SseMessageFactory.done())
        logger.info("流式聊天请求完成 | lastEventId=%s", emitter.last_event_id)

    except TimeoutError:
        # 超时：已交付部分正文 + 统一超时提示，一并落库
        timeout_msg = t(I18nKey.CHAT_TIMEOUT)
        recorder.set_error(timeout_msg)
        logger.warning("流式聊天请求超时")
        yield emitter.emit(
            "error", chat_error_event(ErrorCode.CHAT.TIMEOUT, timeout_msg)
        )
    except asyncio.CancelledError:
        # 客户端已断开，无需 re-raise（避免 ASGI 层记录 500），
        # 让 generator 自然结束；scope.cleanup() 在 finally 中保证执行。
        # 主动取消不展示客户端文案，但已交付内容仍要落库。
        logger.warning("【统计】流式SSE请求被客户端主动取消")
        return
    except Exception as e:
        err_msg = get_safe_error_message(e)
        recorder.set_error(err_msg)
        logger.exception("流式聊天请求失败")
        yield emitter.emit("error", chat_error_event(ErrorCode.CHAT.UNKNOWN, err_msg))
    finally:
        # 请求结束（无论成功/失败/取消）：清理请求上下文，回收线程资源
        scope.cleanup()
        # 失败 / 中断路径兜底落库：DB 存「服务端已交付的内容」。
        # 成功路径已落库则跳过；未尝试或上次失败则再给一次机会
        await recorder.ensure_persisted()
