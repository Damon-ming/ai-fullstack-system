# app-server/src/com/damon/ming/ai/inference/vllm_inference.py

import json
import time
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

        err_msg = ""
        for attempt in range(self.params.max_retries):
            try:
                resp = await self.client.chat.completions.create(**create_kwargs)
                return resp.choices[0].message.content
            except Exception as e:
                err_msg = f"VLLM调用异常: {e!s}"
                wait = 2**attempt
                logger.warning(
                    f"推理重试 {attempt + 1}/{self.params.max_retries}, wait {wait}s | {err_msg}"
                )
                time.sleep(wait)

        logger.error(f"VLLM推理全部重试失败: {err_msg}")
        if response_schema is not None:
            fallback_dict = {
                "answer_content": f"系统调用失败: {err_msg}",
            }
            if reason:
                fallback_dict["reasoning_process"] = ""
            return json.dumps(fallback_dict, ensure_ascii=False)
        return json.dumps({"error": err_msg})

    async def stream_generate(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamToken, None]:
        run_opts = _map_options(options)
        stream = await self.client.chat.completions.create(
            model=model_name, messages=messages, stream=True, **run_opts
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield StreamToken(content=reasoning, type="reasoning")
            content = delta.content
            if content:
                yield StreamToken(content=content, type="content")

    async def check_model_ready(self, model_name: str) -> bool:
        try:
            models = await self.client.models.list()
            model_names = [m.id for m in models.data]
            return model_name in model_names
        except Exception as e:
            logger.error("VLLM模型检测失败:", str(e))
            return False

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "vllm",
            "base_url": self.params.base_url,
            "timeout": self.params.timeout,
        }
