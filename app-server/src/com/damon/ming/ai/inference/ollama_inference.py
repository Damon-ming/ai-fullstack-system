# app-server/src/com/damon/ming/ai/inference/ollama_inference.py

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import ollama
from src.com.damon.ming.ai.inference.base_inference import (
    STREAM_TYPE_CONTENT,
    STREAM_TYPE_REASONING,
    BaseInferenceService,
    InferenceParams,
    StreamToken,
    register_engine,
)
from src.com.damon.ming.log import pin

logger = pin("OllamaInference")


def _map_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """将统一的模型级参数映射为 Ollama API 字段。

    max_tokens → num_predict（Ollama 的输出 token 上限参数名）
    """
    if not options:
        return {}
    mapped = dict(options)
    if "max_tokens" in mapped:
        mapped["num_predict"] = mapped.pop("max_tokens")
    return mapped


@register_engine("ollama")
class OllamaInference(BaseInferenceService):
    def __init__(self, params: InferenceParams):
        super().__init__(params)
        keep_alive = params.extra.get("keep_alive")
        if keep_alive is not None and (
            isinstance(keep_alive, bool)
            or not isinstance(keep_alive, (str, int))
            or (isinstance(keep_alive, str) and not keep_alive.strip())
        ):
            keep_alive = None
        self.keep_alive = keep_alive
        self.client = ollama.AsyncClient(host=params.base_url, timeout=params.timeout)
        logger.info(f"Ollama推理客户端初始化 | url={params.base_url}")

    async def text_generation(
        self,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        model_name: str = "",
    ) -> str:
        run_opts = _map_options(options)
        if reason:
            run_opts["think"] = True
        ollama_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "options": run_opts,
        }
        if response_schema is not None:
            ollama_kwargs["format"] = response_schema
        if self.keep_alive is not None:
            ollama_kwargs["keep_alive"] = self.keep_alive
        # 一次性返回完整响应；只有 stream_generate 使用 Ollama 流式接口。
        ollama_kwargs["stream"] = False

        # 无重试：异常直接抛给上层，由前端自行重试请求
        try:
            response = await self.client.chat(**ollama_kwargs)
            return response.message.content or ""
        except Exception:
            logger.exception("Ollama推理失败")
            raise

    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        reason: bool = False,
        options: dict[str, Any] | None = None,
        model_name: str = "",
    ) -> AsyncGenerator[StreamToken, None]:
        run_opts = _map_options(options)
        if reason:
            run_opts["think"] = True
        chat_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "options": run_opts,
            "stream": True,
        }
        if self.keep_alive is not None:
            chat_kwargs["keep_alive"] = self.keep_alive
        stream = await self.client.chat(**chat_kwargs)
        try:
            async for chunk in stream:
                msg = chunk.get("message", {})
                thinking = msg.get("thinking", "")
                if thinking:
                    yield StreamToken(content=thinking, type=STREAM_TYPE_REASONING)
                content = msg.get("content", "")
                if content:
                    yield StreamToken(content=content, type=STREAM_TYPE_CONTENT)
        except asyncio.CancelledError:
            logger.warning("Ollama stream 收到取消信号，关闭ollama流")
            raise
        finally:
            await stream.close()

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "base_url": self.params.base_url,
            "timeout": self.params.timeout,
        }
