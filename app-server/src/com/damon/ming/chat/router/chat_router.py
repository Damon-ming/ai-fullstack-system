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
    ChatDoneData,
    StreamMessage,
)
from src.com.damon.ming.chat.schemas.bean import ChatRequest
from src.com.damon.ming.log import pin
from sse_starlette.sse import EventSourceResponse

logger = pin("chat.router")

router = APIRouter(prefix="/api/llm", tags=["聊天模块"])

# ========== 全局信号量：控制同时执行LLM推理的并发数量，4090可以调到3~6，看模型大小 ==========
INFER_SEM = asyncio.Semaphore(4)
INFER_WAIT_TIMEOUT = 30

# todo 后期加上
# 加载配置，创建意图识别器
# intention_cfg = IntentionConfig()
# classifier = intention_cfg.create_classifier("default")
# intentions = ["chat_闲聊", "doc_query_知识库检索", "file_upload_上传文件"]
# user_query = "帮我查一下项目方案内容"
# res = classifier.classify(user_query, intention_list=intentions)

SYSTEM_PROMPT_TPL = """
你是严格基于知识库的问答助手，必须遵守以下硬性规则，绝对不能违反：
1. 只能使用【参考知识库】内存在的内容回答用户问题；
2. 如果参考知识库为空、或者没有和用户问题相关的内容，直接只输出：语料库没有相关资料。；
3. 禁止使用你自身内置常识、禁止脑补、禁止推测、禁止编造任何原文不存在的信息；
4. 回答使用标准Markdown格式输出，存在多条内容用有序/无序列表，重点内容加粗，表格原样保留；
5. 回答精简，不要多余解释、不要分析、不要思考过程；
6. 不允许输出无关内容，严格遵守知识库边界。

【参考知识库】
{ref_content}
"""


@router.post("/send/v1")
async def chat(req: Request, body: ChatRequest):
    logger.info(
        "同步聊天请求开始 | query_length=%s | think=%s",
        len(body.query),
        body.think,
    )

    try:
        async with INFER_SEM:
            async with asyncio.timeout(INFER_WAIT_TIMEOUT):
                logger.debug("开始执行同步 RAG 检索")

                # 1. 调用RAG检索，获取拼接完整章节上下文
                ref_content = await asyncio.to_thread(
                    req.app.state.rag_app.query_rag(body.query)
                )

                schema = get_chat_schema(body.think)

                # 2. 填充固定Prompt，构造标准messages数组
                system_prompt = SYSTEM_PROMPT_TPL.format(ref_content=ref_content)
                prompt_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body.query},
                ]

                llm_raw = await req.app.state.infer_service.text_generation(
                    model_name=req.app.state.llm_model_name,
                    messages=prompt_messages,
                    think_flag=body.think,
                    response_schema=schema,
                )

            # 4. 组装返回结构体，think控制是否携带思考过程（当前固定空）
            resp_inner = json.loads(llm_raw)
            logger.info("同步聊天请求完成")
            # 外层统一返回
            return BaseLLMSuccessResponse[BaseLLMSuccessData](
                bizCode=100000, data=BaseLLMSuccessData(result=resp_inner)
            )
    except TimeoutError as e:
        logger.warning("同步聊天请求超时")
        return BaseLLMFailedResponse[BaseLLMFailedData](
            bizCode=300001,
            data=BaseLLMFailedData(error_msg=str(e)),
        )
    except asyncio.CancelledError:
        logger.warning("【统计】同步聊天请求被客户端主动取消")
        raise
    except Exception as e:
        logger.exception("同步聊天请求未知异常")
        return BaseLLMFailedResponse[BaseLLMFailedData](
            bizCode=300002,
            data=BaseLLMFailedData(error_msg=str(e)),
        )


@router.post("/chat/v1")
async def chat_stream(req: Request, body: ChatRequest):
    """流式问答接口，SSE流式输出"""
    logger.info("流式聊天请求开始 | query_length=%s", len(body.query))
    generator = stream_chat_generator(req, body)
    return EventSourceResponse(generator)


async def stream_chat_generator(req: Request, body: ChatRequest):
    try:
        async with INFER_SEM:
            try:
                async with asyncio.timeout(INFER_WAIT_TIMEOUT):
                    logger.debug("开始执行流式 RAG 检索")
                    ref_content = await asyncio.to_thread(
                        req.app.state.rag_app.query_rag(body.query)
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
                        ):
                            # todo 补充hearbeat用:, event添加start(携带元信息)， :id，后期可以做断点续传,retry:重连
                            # todo 空行隔开事件
                            # todo event: delta
                            # todo data: {"bizCode":100000,"data":{...}}
                            # start结构
                            # msgId	本次回答的消息 id	"msg_abc123"
                            # conversationId	会话 id	"conv_456"
                            # model	用的模型	"gpt-4"
                            # createdAt	开始时间戳	1700000000
                            # traceId	链路追踪 id	"trace_xyz"
                            # event: start
                            # data: {
                            #   "bizCode": 100000,
                            #   "data": {
                            #     "msgId": "msg_abc123",
                            #     "conversationId": "conv_456",
                            #     "model": "gpt-4",
                            #     "createdAt": 1700000000,
                            #     "traceId": "trace_xyz"
                            #   }
                            # }
                            delta_msg = StreamMessage[ChatDeltaData](
                                bizCode=100000,
                                event="delta",
                                data=ChatDeltaData(answer_content=token),
                            )
                            yield delta_msg.model_dump_json(ensure_ascii=False)
                    except asyncio.CancelledError:
                        logger.warning("SSE客户端主动断开连接，取消推理任务")
                        raise
            except TimeoutError as e:
                logger.warning("流式聊天请求超时")
                err_msg = StreamMessage[BaseLLMFailedData](
                    bizCode=300001,
                    event="error",
                    data=BaseLLMFailedData(error_msg=str(e)),
                )
                yield err_msg.model_dump_json(ensure_ascii=False)
                return
        # 结束包
        done_msg = StreamMessage[ChatDoneData](
            bizCode=100000, event="done", data=ChatDoneData()
        )
        yield done_msg.model_dump_json(ensure_ascii=False)
        logger.info("流式聊天请求完成")

    except asyncio.CancelledError:
        logger.warning("【统计】流式SSE请求被客户端主动取消")
        raise
    except Exception as e:
        logger.exception("流式聊天请求失败")
        err_msg = StreamMessage[BaseLLMFailedData](
            bizCode=300003,
            event="error",
            data=BaseLLMFailedData(error_msg=str(e)),
        )
        yield err_msg.model_dump_json(ensure_ascii=False)
