# app-server/src/com/damon/ming/router/chat/chat_router.py
import asyncio
import uuid

from fastapi import APIRouter, Request
from src.com.damon.ming.ai.inference.base_inference import STREAM_TYPE_REASONING
from src.com.damon.ming.ai.schemas.response import (
    BaseLLMFailedData,
    BaseLLMFailedResponse,
    BaseLLMSuccessData,
    BaseLLMSuccessResponse,
    ChatDeltaData,
)
from src.com.damon.ming.app.config.inference.inference_runtime_config_loader import (
    ChatConfigLoader,
    ChatLocaleText,
)
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.exception.server_error import get_safe_error_message
from src.com.damon.ming.i18n import get_locale, t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.chat.preflight import (
    check_guardrail_with_timeout,
    check_input,
)
from src.com.damon.ming.router.chat.schemas.bean import ChatRequest
from src.com.damon.ming.router.chat.sse import SseEmitter, SseMessageFactory
from src.com.damon.ming.router.history.service.chat_turn import ChatTurnRecorder
from src.com.damon.ming.utils.time import now
from sse_starlette.sse import EventSourceResponse

logger = pin("chat.router")

router = APIRouter(prefix="/api/llm", tags=["聊天模块"])

# RAG 检索上下文 token 上限（与 vLLM max-model-len 对齐）
# 约束：system(~200) + context_budget + query(~50) + max_tokens(1024) ≤ 2048
# 跑通模式：budget=512 → 总占用 ~1826 ≤ 2048
# 完整模式：换大模型后同步调高（max-model-len 4096 → budget 可设 2048）
MAX_CONTEXT_TOKEN_BUDGET = 512


def _get_chat_text_cfg(app_state) -> ChatLocaleText:
    """获取当前请求 locale 对应的聊天文本配置。"""
    return ChatConfigLoader.resolve_locale_text(app_state.chat_locales, get_locale())


# ── 请求身份（history 落库口径） ────────────────────────────────────


def _request_token(request: Request) -> str:
    """从请求上下文获取当前用户 token（与 history 模块口径一致）。"""
    return getattr(request.state, "ctx", None) and request.state.ctx.token or ""


@router.post("/send/v1")
@limiter.limit("10/minute")
async def chat(request: Request, body: ChatRequest):
    logger.info(
        "同步聊天请求开始 | query_length=%s | reason=%s",
        len(body.query),
        body.reason,
    )

    # 创建请求级上下文，绑定 CancellationToken
    ctx = request.app.state.pool_mgr.create_request_context()

    # 会话 id 提前确定：拦截轮次也要落库，需要会话归属
    conversation_id = body.conversationId or SseMessageFactory.new_conversation_id()
    # 轮次 id：与 SSE 链路同口径，下发给客户端的同时作为落库主键
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"
    # 提问时刻：请求到达即采集，作为全部时延指标的起点
    query_at = now()

    # 本轮交付内容记录器：成功 / 失败 / 中断都用它落库，口径一致
    recorder = ChatTurnRecorder(
        token=_request_token(request),
        turn_id=turn_id,
        conversation_id=conversation_id,
        query=body.query,
        query_at=query_at,
    )

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
        rag_sem = request.app.state.rag_sem
        infer_timeout = request.app.state.infer_timeout
        _chat_cfg = _get_chat_text_cfg(request.app.state)
        system_prompt_tpl = _chat_cfg.system_prompt
        ref_label = _chat_cfg.ref_label
        query_label = _chat_cfg.query_label

        # ── Phase 2: RAG + 推理（共享完整超时预算） ──
        async with asyncio.timeout(infer_timeout):
            logger.debug("开始执行同步 RAG 检索")

            # 1. RAG 检索在推理信号量外执行（自身有线程池保护 + rag_sem 反压）
            async with rag_sem:
                ref_content = await request.app.state.rag_app.query_rag(
                    body.query,
                    max_context_tokens=MAX_CONTEXT_TOKEN_BUDGET,
                    cancellation_token=ctx.cancellation_token,
                )

            # 2. 构造标准messages数组：system prompt 保持纯净（只含指令），
            #    用户数据（参考资料 + 问题）全部放在 user message 中，
            #    避免 ref_content 中的模板占位符或恶意内容污染 system prompt。
            #    消息标签从 YAML 配置读取，与 system prompt 同文件管理。
            prompt_messages = [
                {"role": "system", "content": system_prompt_tpl},
                {
                    "role": "user",
                    "content": f"{ref_label}\n{ref_content}\n\n{query_label}{body.query}",
                },
            ]

            # 3. 仅推理段进入信号量，释放 RAG 等待期间的并发槽
            #    正文为纯文本（无 JSON 约束），推理走模型原生通道
            async with infer_sem:
                llm_raw = await request.app.state.infer_service.text_generation(
                    model_name=request.app.state.llm_model_name,
                    messages=prompt_messages,
                    reason=body.reason,
                    options=dict(request.app.state.llm_options),
                )

            answer = llm_raw.strip()
            recorder.add_content(answer)
            recorder.mark_answered(now())
            logger.info("同步聊天请求完成")

            # 成功路径：本轮对话落库（服务端写入，不依赖客户端回传）
            # 非流式调用观测不到 token 级时刻，first_token_at / reasoning_done_at 留空
            persist_ok = await recorder.persist()

            # 同步链路没有流式缓冲可展示，落库失败只能整体报错
            if not persist_ok:
                return BaseLLMFailedResponse[BaseLLMFailedData](
                    code=ErrorCode.CHAT.PERSIST_FAILED,
                    data=BaseLLMFailedData(error_msg=t(I18nKey.CHAT_PERSIST_FAILED)),
                )

            # 外层统一返回：conversationId 必须回传，客户端才能把后续轮次追加到同一会话
            return BaseLLMSuccessResponse[BaseLLMSuccessData](
                code=ErrorCode.OK,
                data=BaseLLMSuccessData(
                    data={"content": answer, "conversationId": conversation_id}
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

    # 创建请求级上下文，绑定 CancellationToken
    ctx = request.app.state.pool_mgr.create_request_context()

    generator = stream_chat_generator(request, body, ctx)
    return EventSourceResponse(
        generator,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


async def stream_chat_generator(request: Request, body: ChatRequest, ctx):
    """流式问答 SSE 生成器 —— 主流程只关心业务，协议细节交给 SseEmitter

    Args:
        ctx: 请求上下文，包含 CancellationToken。
             请求结束（包括客户端断开）时自动 cleanup。
    """
    emitter = SseEmitter(retry_ms=request.app.state.retry_ms)

    # 会话 id：前端未指定则新建；经 start 事件下发，后续轮次回传追加
    conversation_id = body.conversationId or SseMessageFactory.new_conversation_id()
    # 轮次 id：请求到达即生成，start 事件下发给客户端，同时作为落库主键，
    # 保证「客户端看到的 turnId」与「DB 里的 turn_id」是同一轮
    turn_id = f"turn_{uuid.uuid4().hex[:12]}"

    # 提问时刻：请求到达即采集，作为全部时延指标的起点
    query_at = now()

    # 本轮交付内容记录器：成功 / 失败 / 中断都用它落库，口径一致
    recorder = ChatTurnRecorder(
        token=_request_token(request),
        turn_id=turn_id,
        conversation_id=conversation_id,
        query=body.query,
        query_at=query_at,
    )

    try:
        # ── start 事件在信号量外立即发送，客户端无需排队等待即可感知连接建立 ──
        yield emitter.emit(
            "start",
            SseMessageFactory.start(
                SseMessageFactory.get_start_data(turn_id, conversation_id)
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
        rag_sem = request.app.state.rag_sem
        infer_timeout = request.app.state.infer_timeout
        _chat_cfg = _get_chat_text_cfg(request.app.state)
        system_prompt_tpl = _chat_cfg.system_prompt
        ref_label = _chat_cfg.ref_label
        query_label = _chat_cfg.query_label

        # ── Phase 2: RAG + 推理（共享完整超时预算） ──
        async with asyncio.timeout(infer_timeout):
            logger.debug("开始执行流式 RAG 检索")
            # RAG 在推理信号量外执行（自身有线程池保护 + rag_sem 反压）
            async with rag_sem:
                ref_content = await request.app.state.rag_app.query_rag(
                    body.query,
                    max_context_tokens=MAX_CONTEXT_TOKEN_BUDGET,
                    cancellation_token=ctx.cancellation_token,
                )

            # system prompt 保持纯净（只含指令），用户数据放在 user message 中，
            # 避免 ref_content 中的内容污染 system prompt（防模板注入）。
            # 消息标签从 YAML 配置读取，与 system prompt 同文件管理。
            prompt_messages = [
                {"role": "system", "content": system_prompt_tpl},
                {
                    "role": "user",
                    "content": f"{ref_label}\n{ref_content}\n\n{query_label}{body.query}",
                },
            ]
            logger.debug("prompt_messages:\n%s", prompt_messages)

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
