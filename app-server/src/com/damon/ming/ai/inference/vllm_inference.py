# app-server/src/com/damon/ming/ai/inference/vllm_inference.py

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
    StreamToken,
    register_engine,
)
from src.com.damon.ming.log import pin

logger = pin("VLLMInference")


def _map_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """将统一的模型级参数映射为 OpenAI API 字段。

    num_ctx → max_tokens（OpenAI 兼容接口的 token 上限参数名）
    """
    if not options:
        return {}
    mapped = dict(options)
    if "num_ctx" in mapped:
        mapped["max_tokens"] = mapped.pop("num_ctx")
    return mapped


@register_engine("vllm")
class VLLMInference(BaseInferenceService):
    def __init__(self, params: InferenceParams):
        super().__init__(params)
        self.client = AsyncOpenAI(
            base_url=params.base_url,
            api_key=params.api_key,
            timeout=params.timeout,
        )
        logger.info(f"VLLM推理客户端初始化 | url={params.base_url}")

    async def text_generation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        run_opts = _map_options(options)

        create_kwargs = {"model": model_name, "messages": messages, **run_opts}
        if response_schema:
            create_kwargs["response_format"] = {
                "type": "json_object",
                "schema": response_schema,
            }

        # 无重试：异常直接抛给上层，由前端自行重试请求
        resp = await self.client.chat.completions.create(**create_kwargs)
        return resp.choices[0].message.content

    async def stream_generate(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamToken, None]:
        run_opts = _map_options(options)
        create_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            **run_opts,
        }
        if response_schema:
            create_kwargs["response_format"] = {
                "type": "json_object",
                "schema": response_schema,
            }
        stream = await self.client.chat.completions.create(**create_kwargs)
        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield StreamToken(content=reasoning, type="reasoning")
                content = delta.content
                if content:
                    yield StreamToken(content=content, type="content")
        except asyncio.CancelledError:
            logger.warning("VLLM stream 收到取消信号，关闭流")
            raise
        finally:
            # 取消时事件循环可能不再调度 await，加容错避免 finally 异常
            try:
                await stream.close()
            except asyncio.CancelledError:
                logger.warning("VLLM stream 取消后关闭被中断，跳过")
            except Exception as e:
                logger.warning("VLLM stream 关闭异常 | error=%s", e)

    async def check_model_ready(self, model_name: str) -> bool:
        try:
            models = await self.client.models.list()
            model_names = [m.id for m in models.data]
            return model_name in model_names
        except Exception as e:
            logger.error("VLLM模型检测失败: %s", e)
            return False

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "vllm",
            "base_url": self.params.base_url,
            "timeout": self.params.timeout,
        }
