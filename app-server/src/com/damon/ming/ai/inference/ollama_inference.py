# app-server/src/com/damon/ming/ai/inference/ollama_inference.py

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import ollama
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
    StreamToken,
    register_engine,
)
from src.com.damon.ming.log import pin

logger = pin("OllamaInference")


@register_engine("ollama")
class OllamaInference(BaseInferenceService):
    def __init__(self, params: InferenceParams):
        super().__init__(params)
        self.client = ollama.AsyncClient(host=params.base_url, timeout=params.timeout)
        logger.info(f"Ollama推理客户端初始化 | url={params.base_url}")

    async def text_generation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        run_opts = dict(options) if options else {}
        if reason:
            run_opts["think"] = True
        ollama_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "options": run_opts,
        }
        if response_schema is not None:
            ollama_kwargs["format"] = response_schema
        ollama_kwargs["stream"] = True

        # 无重试：异常直接抛给上层，由前端自行重试请求
        stream = await self.client.chat(**ollama_kwargs)
        try:
            thinking_parts: list[str] = []
            content_parts: list[str] = []
            async for chunk in stream:
                msg = chunk.get("message", {})
                thinking = msg.get("thinking", "")
                if thinking:
                    thinking_parts.append(thinking)
                content = msg.get("content", "")
                if content:
                    content_parts.append(content)
            await stream.close()
            if reason and thinking_parts:
                thinking_text = "".join(thinking_parts)
                answer_text = "".join(content_parts)
                return json.dumps(
                    {
                        "reasoning_process": thinking_text,
                        "answer_content": answer_text,
                    },
                    ensure_ascii=False,
                )
            return "".join(content_parts)
        except asyncio.CancelledError:
            logger.warning("text_generation 任务被取消，关闭ollama流")
            await stream.close()
            raise
        except Exception:
            logger.exception("Ollama推理失败")
            await stream.close()
            raise

    async def stream_generate(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamToken, None]:
        run_opts = dict(options) if options else {}
        if reason:
            run_opts["think"] = True
        stream = await self.client.chat(
            model=model_name,
            messages=messages,
            options=run_opts,
            stream=True,
            keep_alive="30m",
        )
        try:
            async for chunk in stream:
                msg = chunk.get("message", {})
                thinking = msg.get("thinking", "")
                if thinking:
                    yield StreamToken(content=thinking, type="reasoning")
                content = msg.get("content", "")
                if content:
                    yield StreamToken(content=content, type="content")
        except asyncio.CancelledError:
            logger.warning("Ollama stream 收到取消信号，关闭ollama流")
            raise
        finally:
            await stream.close()

    async def warmup(self, model_name: str) -> None:
        try:
            await self.client.chat(
                model=model_name,
                messages=[{"role": "user", "content": "ping"}],
                options={"num_predict": 1},
                keep_alive="30m",
            )
            logger.info("Ollama模型预热完成 | model=%s | keep_alive=30m", model_name)
        except Exception:
            logger.exception("Ollama模型预热失败 | model=%s", model_name)

    async def check_model_ready(self, model_name: str) -> bool:
        try:
            res = await self.client.list()
            model_list = [m["name"] for m in res.get("models", [])]
            return model_name in model_list
        except Exception as e:
            logger.error("模型检测失败: %s", e)
            return False

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "base_url": self.params.base_url,
            "timeout": self.params.timeout,
        }
