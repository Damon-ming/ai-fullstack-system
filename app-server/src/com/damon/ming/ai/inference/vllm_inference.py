# app-server/src/com/damon/ming/ai/inference/vllm_inference.py

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI
from src.com.damon.ming.ai.inference.base_inference import BaseInferenceService
from src.com.damon.ming.log import pin

logger = pin("VLLMInference")


class VLLMInference(BaseInferenceService):
    def __init__(
        self,
        base_url: str = "http://vllm:8000/v1",
        api_key: str = "dummy",
        timeout: int = 90,
        max_retries: int = 3,
        temperature: float = 0.1,
        top_p: float = 0.9,
        num_ctx: int = 4096,
    ):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_options = {
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": num_ctx,
        }
        logger.info(f"VLLM推理客户端初始化 | url={base_url}")

    async def text_generation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        think_flag: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        run_opts = self.default_options.copy()
        if options:
            run_opts.update(options)

        create_kwargs = {"model": model_name, "messages": messages, **run_opts}
        # VLLM OpenAI兼容json schema输出
        if response_schema:
            create_kwargs["response_format"] = {
                "type": "json_object",
                "schema": response_schema,
            }

        err_msg = ""
        for attempt in range(self.max_retries):
            try:
                resp = await self.client.chat.completions.create(**create_kwargs)
                return resp.choices[0].message.content
            except Exception as e:
                err_msg = f"VLLM调用异常: {e!s}"
                wait = 2**attempt
                logger.warning(
                    f"推理重试 {attempt + 1}/{self.max_retries}, wait {wait}s | {err_msg}"
                )
                time.sleep(wait)

        logger.error(f"VLLM推理全部重试失败: {err_msg}")
        if response_schema is not None:
            fallback_dict = {
                "answer_content": f"系统调用失败: {err_msg}",
            }
            if think_flag:
                fallback_dict["thinking_process"] = ""
            return json.dumps(fallback_dict, ensure_ascii=False)
        return json.dumps({"error": err_msg})

    async def stream_generate(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        run_opts = self.default_options.copy()
        if options:
            run_opts.update(options)
        stream = await self.client.chat.completions.create(
            model=model_name, messages=messages, stream=True, **run_opts
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

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
            "base_url": self.base_url,
            "timeout": self.timeout,
            "default_options": self.default_options,
        }
