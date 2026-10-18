# app-server/src/com/damon/ming/chat/router/chat_router.py
import asyncio
import json

from fastapi import APIRouter, Request
from src.com.damon.ming.ai.schemas.inference_params import get_chat_schema
from src.com.damon.ming.ai.schemas.response import (
    BaseLLMFailedData,
    BaseLLMFailedResponse,
    BaseLLMSuccessData,
    BaseLLMSuccessResponse,
    ChatDeltaData,
)
from src.com.damon.ming.ai.security import InputValidator
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.chat.schemas.bean import ChatRequest
from src.com.damon.ming.router.chat.sse import SseEmitter, SseMessageFactory
from sse_starlette.sse import EventSourceResponse

logger = pin("chat.router")

router = APIRouter(prefix="/api/llm", tags=["聊天模块"])

# 轻量级输入校验器（模块级单例，无状态，可并发）
_input_validator = InputValidator()


def _check_input(query: str) -> BaseLLMFailedResponse | None:
    """前置输入校验（纯本地规则，零 IO，微秒级）。

    在调用 LLM 护栏之前快速拦截无效/攻击性输入，避免浪费护栏推理资源。
    校验通过返回 None，不通过返回失败响应。
    """
    result = _input_validator.validate(query)
    if not result.passed:
        logger.warning("输入校验拦截 | rule=%s | reason=%s", result.rule, result.reason)
        return BaseLLMFailedResponse[BaseLLMFailedData](
            code=ErrorCode.CHAT.GUARDRAIL_BLOCKED,
            data=BaseLLMFailedData(error_msg=result.reason),
        )
    return None


async def _check_guardrail(app_state, query: str) -> BaseLLMFailedResponse | None:
    """执行护栏检测，不通过时返回失败响应，通过时返回 None。"""
    guardrail = getattr(app_state, "guardrail", None)
    if guardrail is None:
        return None

    result = await guardrail.check(query)
    if not result.passed:
        logger.warning("护栏拦截用户输入 | reason=%s", result.reason)
        return BaseLLMFailedResponse[BaseLLMFailedData](
            code=ErrorCode.CHAT.GUARDRAIL_BLOCKED,
            data=BaseLLMFailedData(error_msg=result.reason or "输入内容被安全策略拦截"),
        )
    return None


async def _guardrail_check_with_timeout(
    app_state, query: str
) -> BaseLLMFailedResponse | None:
    """护栏检测 + 独立超时 + 信号量限流（超时 fail-open 放行）。

    抽取为独立函数，供同步 / 流式接口复用，避免重复代码。
    guardrail_sem 保护护栏 LLM 调用不被打爆。
    """
    guardrail_timeout = app_state.guardrail_timeout
    guardrail_sem = getattr(app_state, "guardrail_sem", None)
    try:
        async with asyncio.timeout(guardrail_timeout):
            if guardrail_sem is not None:
                async with guardrail_sem:
                    return await _check_guardrail(app_state, query)
            else:
                return await _check_guardrail(app_state, query)
    except TimeoutError:
        logger.warning("护栏检测超时，fail-open 放行 | timeout=%ds", guardrail_timeout)
        return None


@router.post("/send/v1")
@limiter.limit("10/minute")
async def chat(req: Request, body: ChatRequest):
    logger.info(
        "同步聊天请求开始 | query_length=%s | reason=%s",
        len(body.query),
        body.reason,
    )

    # 创建请求级上下文，绑定 CancellationToken
    ctx = req.app.state.pool_mgr.create_request_context()

    try:
        # ── Phase 0: 前置输入校验（纯本地规则，零 IO，拦截无效/攻击输入） ──
        input_blocked = _check_input(body.query)
        if input_blocked is not None:
            return input_blocked

        # ── Phase 1: 护栏检测（独立超时，超时 fail-open 放行） ──
        blocked = await _guardrail_check_with_timeout(req.app.state, body.query)
        if blocked is not None:
            return blocked

        infer_sem = req.app.state.infer_sem
        rag_sem = req.app.state.rag_sem
        infer_timeout = req.app.state.infer_timeout
        system_prompt_tpl = req.app.state.system_prompt_tpl

        # ── Phase 2: RAG + 推理（共享完整超时预算） ──
        async with asyncio.timeout(infer_timeout):
            logger.debug("开始执行同步 RAG 检索")

            # 1. RAG 检索在推理信号量外执行（自身有线程池保护 + rag_sem 反压）
            async with rag_sem:
                ref_content = await req.app.state.rag_app.query_rag(
                    body.query,
                    cancellation_token=ctx.cancellation_token,
                )

            schema = get_chat_schema(body.reason)

            # 2. 填充固定Prompt，构造标准messages数组
            system_prompt = system_prompt_tpl.replace("{ref_content}", ref_content, 1)
            prompt_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.query},
            ]

            # 3. 仅推理段进入信号量，释放 RAG 等待期间的并发槽
            async with infer_sem:
                llm_raw = await req.app.state.infer_service.text_generation(
                    model_name=req.app.state.llm_model_name,
                    messages=prompt_messages,
                    reason=body.reason,
                    response_schema=schema,
                    options=dict(req.app.state.llm_options),
                )

            # 4. 组装返回结构体，think控制是否携带思考过程（当前固定空）
            resp_inner = json.loads(llm_raw)
            logger.info("同步聊天请求完成")
            # 外层统一返回
            return BaseLLMSuccessResponse[BaseLLMSuccessData](
                code=ErrorCode.OK, data=BaseLLMSuccessData(data=resp_inner)
            )
    except TimeoutError as e:
        logger.warning("同步聊天请求超时")
        return BaseLLMFailedResponse[BaseLLMFailedData](
            code=ErrorCode.CHAT.TIMEOUT,
            data=BaseLLMFailedData(error_msg=str(e)),
        )
    except asyncio.CancelledError:
        logger.warning("【统计】同步聊天请求被客户端主动取消")
        raise
    except Exception as e:
        logger.exception("同步聊天请求未知异常")
        return BaseLLMFailedResponse[BaseLLMFailedData](
            code=ErrorCode.CHAT.UNKNOWN,
            data=BaseLLMFailedData(error_msg=str(e)),
        )
    finally:
        # 请求结束（无论成功/失败/取消）：清理请求上下文，回收线程资源
        ctx.cleanup()


@router.post("/chat/v1")
@limiter.limit("10/minute")
async def chat_stream(req: Request, body: ChatRequest):
    """流式问答接口，SSE流式输出（W3C EventSource 标准格式）"""
    logger.info("流式聊天请求开始 | query_length=%s", len(body.query))

    # 创建请求级上下文，绑定 CancellationToken
    ctx = req.app.state.pool_mgr.create_request_context()

    generator = stream_chat_generator(req, body, ctx)
    return EventSourceResponse(
        generator,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


async def stream_chat_generator(req: Request, body: ChatRequest, ctx):
    """流式问答 SSE 生成器 —— 主流程只关心业务，协议细节交给 SseEmitter

    Args:
        ctx: 请求上下文，包含 CancellationToken。
             请求结束（包括客户端断开）时自动 cleanup。
    """
    emitter = SseEmitter(retry_ms=req.app.state.retry_ms)

    try:
        # ── start 事件在信号量外立即发送，客户端无需排队等待即可感知连接建立 ──
        yield emitter.emit(
            "start",
            SseMessageFactory.start(
                SseMessageFactory.get_start_data(req.app.state.llm_model_name)
            ),
            retry=True,
        )

        # ── Phase 0: 前置输入校验（纯本地规则，零 IO，拦截无效/攻击输入） ──
        input_blocked = _check_input(body.query)
        if input_blocked is not None:
            yield emitter.emit(
                "error",
                SseMessageFactory.error(
                    ErrorCode.CHAT.GUARDRAIL_BLOCKED,
                    BaseLLMFailedData(
                        error_msg=input_blocked.data.error_msg
                        if input_blocked.data
                        else "输入校验未通过"
                    ),
                ),
            )
            return

        # ── Phase 1: 护栏检测（独立超时，超时 fail-open 放行） ──
        blocked_resp = await _guardrail_check_with_timeout(req.app.state, body.query)
        if blocked_resp is not None:
            yield emitter.emit(
                "error",
                SseMessageFactory.error(
                    ErrorCode.CHAT.GUARDRAIL_BLOCKED,
                    BaseLLMFailedData(
                        error_msg=blocked_resp.data.error_msg
                        if blocked_resp.data
                        else "输入内容被安全策略拦截"
                    ),
                ),
            )
            return

        infer_sem = req.app.state.infer_sem
        rag_sem = req.app.state.rag_sem
        infer_timeout = req.app.state.infer_timeout
        system_prompt_tpl = req.app.state.system_prompt_tpl

        # ── Phase 2: RAG + 推理（共享完整超时预算） ──
        async with asyncio.timeout(infer_timeout):
            logger.debug("开始执行流式 RAG 检索")
            # RAG 在推理信号量外执行（自身有线程池保护 + rag_sem 反压）
            async with rag_sem:
                ref_content = await req.app.state.rag_app.query_rag(
                    body.query,
                    cancellation_token=ctx.cancellation_token,
                )

            system_prompt = system_prompt_tpl.replace("{ref_content}", ref_content, 1)
            prompt_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.query},
            ]
            logger.debug("prompt_messages:\n%s", prompt_messages)

            # 复用同步接口的 schema 构造，约束 LLM 流式输出为结构化 JSON
            schema = get_chat_schema(body.reason)

            # 仅推理段进入信号量，释放 RAG 等待期间的并发槽
            async with infer_sem:
                try:
                    async for token in req.app.state.infer_service.stream_generate(
                        model_name=req.app.state.llm_model_name,
                        messages=prompt_messages,
                        reason=body.reason,
                        response_schema=schema,
                        options=dict(req.app.state.llm_options),
                    ):
                        # 根据 token 类型发射不同事件：
                        #   reasoning → event: "reasoning"（推理过程）
                        #   content   → event: "delta"（正文回答）
                        event_name = (
                            "reasoning" if token.type == "reasoning" else "delta"
                        )
                        yield emitter.emit(
                            event_name,
                            SseMessageFactory.delta(
                                ChatDeltaData(content=token.content)
                            ),
                        )
                except asyncio.CancelledError:
                    logger.warning("SSE客户端主动断开连接，取消推理任务")
                    raise

        # ── done 事件（结束包） ──
        yield emitter.emit("done", SseMessageFactory.done())
        logger.info("流式聊天请求完成 | lastEventId=%s", emitter.last_event_id)

    except TimeoutError as e:
        logger.warning("流式聊天请求超时")
        yield emitter.emit(
            "error",
            SseMessageFactory.error(
                ErrorCode.CHAT.TIMEOUT, BaseLLMFailedData(error_msg=str(e))
            ),
        )
    except asyncio.CancelledError:
        logger.warning("【统计】流式SSE请求被客户端主动取消")
        raise
    except Exception as e:
        logger.exception("流式聊天请求失败")
        yield emitter.emit(
            "error",
            SseMessageFactory.error(
                ErrorCode.CHAT.UNKNOWN, BaseLLMFailedData(error_msg=str(e))
            ),
        )
    finally:
        # 请求结束（无论成功/失败/取消）：清理请求上下文，回收线程资源
        ctx.cleanup()
