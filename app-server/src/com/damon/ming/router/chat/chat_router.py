# app-server/src/com/damon/ming/router/chat/chat_router.py
import asyncio

from fastapi import APIRouter, Request
from src.com.damon.ming.ai.inference.base_inference import STREAM_TYPE_REASONING
from src.com.damon.ming.ai.schemas.response import (
    BaseLLMFailedData,
    BaseLLMFailedResponse,
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
from src.com.damon.ming.router.chat.preflight import (
    check_guardrail_with_timeout,
    check_input,
)
from src.com.damon.ming.router.chat.schemas.bean import ChatRequest
from src.com.damon.ming.router.chat.service.chat_core import build_prompt_messages
from src.com.damon.ming.router.chat.service.turn_context import (
    ChatTurnContext,
    create_turn,
)
from src.com.damon.ming.router.chat.sse import SseEmitter, SseMessageFactory
from src.com.damon.ming.utils.time import now
from sse_starlette.sse import EventSourceResponse

logger = pin("chat.router")

router = APIRouter(prefix="/api/llm", tags=["聊天模块"])


@router.post("/send/v1")
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest):
    logger.info(
        "同步聊天请求开始 | query_length=%s | reason=%s",
        len(body.query),
        body.reason,
    )

    # 一轮对话的上下文：请求上下文 + 会话/轮次 id + 提问时刻 + 落库记录器
    turn = create_turn(request, body)
    recorder = turn.recorder
    ctx = turn.request_ctx

    try:
        # ── Phase 0: 前置输入校验（纯本地规则，零 IO，拦截无效/攻击输入） ──
        input_blocked = check_input(body.query)
        if input_blocked is not None:
            # 拦截文案是用户实际看到的一轮回答，入库为正文
            recorder.add_content(
                input_blocked.data.error_msg if input_blocked.data else ""
            )
            await recorder.persist()
            return input_blocked

        # ── Phase 1: 护栏检测（独立超时，超时 fail-open 放行） ──
        blocked = await check_guardrail_with_timeout(request.app.state, body.query)
        if blocked is not None:
            recorder.add_content(blocked.data.error_msg if blocked.data else "")
            await recorder.persist()
            return blocked

        infer_sem = request.app.state.infer_sem
        infer_timeout = request.app.state.infer_timeout

        # ── Phase 2: RAG + 推理（共享完整超时预算） ──
        async with asyncio.timeout(infer_timeout):
            prompt_messages = await build_prompt_messages(
                request.app.state, body.query, ctx.cancellation_token
            )

            # 仅推理段进入信号量，释放 RAG 等待期间的并发槽。
            # 同步链路同样走流式通道再缓冲拼接：reasoning 不再被丢弃，
            # first_token_at / reasoning_done_at 等时延指标也得以采集。
            # 正文为纯文本（无 JSON 约束），推理走模型原生通道。
            async with infer_sem:
                async for token in request.app.state.infer_service.stream_generate(
                    model_name=request.app.state.llm_model_name,
                    messages=prompt_messages,
                    reason=body.reason,
                    options=dict(request.app.state.llm_options),
                ):
                    recorder.record_token(token.type, token.content, now())

        recorder.mark_answered(now())
        logger.info("同步聊天请求完成")

        # 成功路径：本轮对话落库（服务端写入，不依赖客户端回传）
        persist_ok = await recorder.persist()

        # 同步链路没有流式缓冲可展示，落库失败只能整体报错
        if not persist_ok:
            return BaseLLMFailedResponse[BaseLLMFailedData](
                code=ErrorCode.CHAT.PERSIST_FAILED,
                data=BaseLLMFailedData(error_msg=t(I18nKey.CHAT_PERSIST_FAILED)),
            )

        # 外层统一返回：conversationId 必须回传，客户端才能把后续轮次追加到同一会话。
        # reasoning 与流式链路同口径：模型未进思考模式时为空串。
        return BaseLLMSuccessResponse[BaseLLMSuccessData](
            code=ErrorCode.OK,
            data=BaseLLMSuccessData(
                data={
                    "content": recorder.content,
                    "reasoning": recorder.reasoning,
                    "conversationId": turn.conversation_id,
                }
            ),
        )
    except TimeoutError:
        timeout_msg = t(I18nKey.CHAT_TIMEOUT)
        recorder.set_error(timeout_msg)
        logger.warning("同步聊天请求超时")
        return BaseLLMFailedResponse[BaseLLMFailedData](
            code=ErrorCode.CHAT.TIMEOUT,
            data=BaseLLMFailedData(error_msg=timeout_msg),
        )
    except asyncio.CancelledError:
        # 主动取消：不展示客户端文案，但已交付内容仍要落库
        logger.warning("【统计】同步聊天请求被客户端主动取消")
        raise
    except Exception as e:
        err_msg = get_safe_error_message(e)
        recorder.set_error(err_msg)
        logger.exception("同步聊天请求未知异常")
        return BaseLLMFailedResponse[BaseLLMFailedData](
            code=ErrorCode.CHAT.UNKNOWN,
            data=BaseLLMFailedData(error_msg=err_msg),
        )
    finally:
        # 请求结束（无论成功/失败/取消）：清理请求上下文，回收线程资源
        ctx.cleanup()
        # 失败 / 中断路径兜底落库：DB 存「服务端已交付的内容」
        if not recorder.attempted:
            await recorder.persist()


@router.post("/chat/v1")
@limiter.limit("10/minute")
async def chat_stream(request: Request, body: ChatRequest):
    """流式问答接口，SSE流式输出（W3C EventSource 标准格式）"""
    logger.info("流式聊天请求开始 | query_length=%s", len(body.query))

    # 一轮对话的上下文：请求上下文 + 会话/轮次 id + 提问时刻 + 落库记录器
    turn = create_turn(request, body)

    return EventSourceResponse(
        stream_chat_generator(request, body, turn),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


async def stream_chat_generator(
    request: Request, body: ChatRequest, turn: ChatTurnContext
):
    """流式问答 SSE 生成器 —— 主流程只关心业务，协议细节交给 SseEmitter

    Args:
        turn: 一轮对话的上下文，含请求上下文（CancellationToken，
              请求结束包括客户端断开时由 finally cleanup）与落库记录器。
    """
    emitter = SseEmitter(retry_ms=request.app.state.retry_ms)
    recorder = turn.recorder
    ctx = turn.request_ctx

    try:
        # ── start 事件在信号量外立即发送，客户端无需排队等待即可感知连接建立 ──
        yield emitter.emit(
            "start",
            SseMessageFactory.start(
                SseMessageFactory.get_start_data(turn.turn_id, turn.conversation_id)
            ),
            retry=True,
        )

        # ── Phase 0: 前置输入校验（纯本地规则，零 IO，拦截无效/攻击输入） ──
        input_blocked = check_input(body.query)
        if input_blocked is not None:
            blocked_msg = (
                input_blocked.data.error_msg
                if input_blocked.data
                else t(I18nKey.VALIDATOR_EMPTY_INPUT)
            )
            # 拦截文案是用户实际看到的一轮回答：走正常 delta/done 通道，
            # 并入库为正文（不是 error_msg），保证刷新后聊天室与历史一致
            recorder.add_content(blocked_msg)
            await recorder.persist()
            yield emitter.emit(
                "delta",
                SseMessageFactory.delta(ChatDeltaData(content=blocked_msg)),
            )
            yield emitter.emit("done", SseMessageFactory.done())
            return

        # ── Phase 1: 护栏检测（独立超时，超时 fail-open 放行） ──
        blocked_resp = await check_guardrail_with_timeout(request.app.state, body.query)
        if blocked_resp is not None:
            blocked_msg = (
                blocked_resp.data.error_msg
                if blocked_resp.data
                else t(I18nKey.GUARDRAIL_BLOCKED)
            )
            recorder.add_content(blocked_msg)
            await recorder.persist()
            yield emitter.emit(
                "delta",
                SseMessageFactory.delta(ChatDeltaData(content=blocked_msg)),
            )
            yield emitter.emit("done", SseMessageFactory.done())
            return

        infer_sem = request.app.state.infer_sem
        infer_timeout = request.app.state.infer_timeout

        # ── Phase 2: RAG + 推理（共享完整超时预算） ──
        async with asyncio.timeout(infer_timeout):
            prompt_messages = await build_prompt_messages(
                request.app.state, body.query, ctx.cancellation_token
            )

            # 仅推理段进入信号量，释放 RAG 等待期间的并发槽
            # CancelledError 不加内层捕获，直接穿透到外层统一处理，
            # 避免重复日志并确保 infer_service 内部 finally 能正确关闭 vLLM 流。
            # 正文为纯文本（无 JSON 约束），推理走模型原生通道。
            async with infer_sem:
                async for token in request.app.state.infer_service.stream_generate(
                    model_name=request.app.state.llm_model_name,
                    messages=prompt_messages,
                    reason=body.reason,
                    options=dict(request.app.state.llm_options),
                ):
                    # 根据 token 类型发射不同事件：
                    #   reasoning → event: "reasoning"（推理过程）
                    #   content   → event: "delta"（正文回答）
                    recorder.record_token(token.type, token.content, now())
                    event_name = (
                        "reasoning" if token.type == STREAM_TYPE_REASONING else "delta"
                    )
                    yield emitter.emit(
                        event_name,
                        SseMessageFactory.delta(ChatDeltaData(content=token.content)),
                    )

            recorder.mark_answered(now())

            # 成功路径：本轮对话落库（服务端写入，不依赖客户端回传）
            # 推理文本随轮次一并持久化，不再只存正文
            persist_ok = await recorder.persist()

            # 回答已完整交付，但历史没写进去：用专属错误码区分「模型失败」
            # 与「存不下」，避免客户端把已显示的回答当成模型没答上
            if not persist_ok:
                yield emitter.emit(
                    "error",
                    SseMessageFactory.error(
                        ErrorCode.CHAT.PERSIST_FAILED,
                        BaseLLMFailedData(error_msg=t(I18nKey.CHAT_PERSIST_FAILED)),
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
            "error",
            SseMessageFactory.error(
                ErrorCode.CHAT.TIMEOUT,
                BaseLLMFailedData(error_msg=timeout_msg),
            ),
        )
    except asyncio.CancelledError:
        # 客户端已断开，无需 re-raise（避免 ASGI 层记录 500），
        # 让 generator 自然结束；ctx.cleanup() 在 finally 中保证执行。
        # 主动取消不展示客户端文案，但已交付内容仍要落库。
        logger.warning("【统计】流式SSE请求被客户端主动取消")
        return
    except Exception as e:
        err_msg = get_safe_error_message(e)
        recorder.set_error(err_msg)
        logger.exception("流式聊天请求失败")
        yield emitter.emit(
            "error",
            SseMessageFactory.error(
                ErrorCode.CHAT.UNKNOWN,
                BaseLLMFailedData(error_msg=err_msg),
            ),
        )
    finally:
        # 请求结束（无论成功/失败/取消）：清理请求上下文，回收线程资源
        ctx.cleanup()
        # 失败 / 中断路径兜底落库：DB 存「服务端已交付的内容」，
        # 成功路径已在上面落库，这里不重复写
        if not recorder.attempted:
            await recorder.persist()
