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
from src.com.damon.ming.app.config.ai.chat_config_loader import ChatConfigLoader
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.chat.schemas.bean import ChatRequest
from src.com.damon.ming.router.chat.sse import SseEmitter, SseMessageFactory
from sse_starlette.sse import EventSourceResponse

logger = pin("chat.router")

router = APIRouter(prefix="/api/llm", tags=["聊天模块"])


def _init_chat_config() -> tuple[asyncio.Semaphore, int, int, str]:
    """从 YAML 加载聊天配置，返回 (信号量, 超时秒数, 重连毫秒数, 系统prompt)。"""
    configs = ChatConfigLoader().load_all()
    cfg = configs.get("default") or configs[next(iter(configs.keys()))]
    sem = asyncio.Semaphore(cfg.infer_concurrency)
    return sem, cfg.infer_timeout, cfg.retry_ms, cfg.system_prompt


INFER_SEM, INFER_WAIT_TIMEOUT, RETRY_MS, SYSTEM_PROMPT_TPL = _init_chat_config()


@router.post("/send/v1")
async def chat(req: Request, body: ChatRequest):
    logger.info(
        "同步聊天请求开始 | query_length=%s | reason=%s",
        len(body.query),
        body.reason,
    )

    # 创建请求级上下文，绑定 CancellationToken
    ctx = req.app.state.pool_mgr.create_request_context()

    try:
        async with INFER_SEM:
            async with asyncio.timeout(INFER_WAIT_TIMEOUT):
                logger.debug("开始执行同步 RAG 检索")

                # 1. 调用RAG检索，获取拼接完整章节上下文（传递取消令牌）
                #    取消时 query_rag 直接抛出 CancelledError，被下方 except 捕获
                ref_content = await req.app.state.rag_app.query_rag(
                    body.query,
                    cancellation_token=ctx.cancellation_token,
                )

                schema = get_chat_schema(body.reason)

                # 2. 填充固定Prompt，构造标准messages数组
                system_prompt = SYSTEM_PROMPT_TPL.format(ref_content=ref_content)
                prompt_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body.query},
                ]

                llm_raw = await req.app.state.infer_service.text_generation(
                    model_name=req.app.state.llm_model_name,
                    messages=prompt_messages,
                    reason=body.reason,
                    response_schema=schema,
                    options=req.app.state.llm_options,
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
    emitter = SseEmitter(retry_ms=RETRY_MS)

    try:
        # ── start 事件在信号量外立即发送，客户端无需排队等待即可感知连接建立 ──
        yield emitter.emit(
            "start",
            SseMessageFactory.start(
                SseMessageFactory.get_start_data(req.app.state.llm_model_name)
            ),
            retry=True,
        )

        async with INFER_SEM:
            try:
                async with asyncio.timeout(INFER_WAIT_TIMEOUT):
                    logger.debug("开始执行流式 RAG 检索")
                    # 取消时 query_rag 直接抛出 CancelledError，被下方 except 捕获
                    ref_content = await req.app.state.rag_app.query_rag(
                        body.query,
                        cancellation_token=ctx.cancellation_token,
                    )

                    system_prompt = SYSTEM_PROMPT_TPL.format(ref_content=ref_content)
                    prompt_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": body.query},
                    ]
                    logger.debug("prompt_messages:\n%s", prompt_messages)

                    try:
                        async for token in req.app.state.infer_service.stream_generate(
                            model_name=req.app.state.llm_model_name,
                            messages=prompt_messages,
                            reason=body.reason,
                            options=req.app.state.llm_options,
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
            except TimeoutError as e:
                logger.warning("流式聊天请求超时")
                yield emitter.emit(
                    "error",
                    SseMessageFactory.error(
                        ErrorCode.CHAT.TIMEOUT, BaseLLMFailedData(error_msg=str(e))
                    ),
                )
                return

        # ── done 事件（结束包） ──
        yield emitter.emit("done", SseMessageFactory.done())
        logger.info("流式聊天请求完成 | lastEventId=%s", emitter.last_event_id)

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
