# app-server/src/com/damon/ming/ai/inference/inference_gateway.py
"""按业务 role 路由到已装配的推理引擎。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any

from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    StreamToken,
)


class InferenceGateway:
    """统一推理入口。引擎由启动配置装配；调用方只需声明 role。"""

    def __init__(
        self,
        roles: dict[str, Any],
        inference_semaphore: asyncio.Semaphore,
    ):
        if not roles:
            raise ValueError("InferenceGateway 至少需要一个已配置 role")
        self._roles = dict(roles)
        self._inference_semaphore = inference_semaphore

    def get(self, role: str) -> RoleInference:
        """按配置名称获取推理入口，供动态角色使用。"""
        if role not in self._roles:
            raise ValueError(f"未配置推理 role: {role}")
        return RoleInference(self, role)

    def get_inference(self) -> RoleInference:
        """获取主回答模型的推理入口。"""
        return self.get("inference")

    def get_guardrail(self) -> RoleInference:
        """获取护栏模型的推理入口。"""
        return self.get("guardrail")

    def get_summary(self) -> RoleInference:
        """获取摘要模型的推理入口。"""
        return self.get("summary")

    def _resolve(self, role: str) -> tuple[BaseInferenceService, str, dict[str, Any]]:
        try:
            entry = self._roles[role]
        except KeyError as exc:
            raise ValueError(f"未配置推理 role: {role}") from exc
        return entry.engine, entry.model_name, dict(entry.options)

    async def generate(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        engine, model_name, role_options = self._resolve(role)
        role_options.update(options or {})

        async def call() -> str:
            return await engine.text_generation(
                model_name=model_name,
                messages=messages,
                reason=reason,
                response_schema=response_schema,
                options=role_options,
            )

        async with (
            asyncio.timeout(self._roles[role].timeout_seconds),
            self._inference_semaphore,
        ):
            return await call()

    async def stream(
        self,
        role: str,
        messages: list[dict[str, str]],
        *,
        reason: bool = False,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamToken, None]:
        engine, model_name, role_options = self._resolve(role)
        role_options.update(options or {})

        async with (
            asyncio.timeout(self._roles[role].timeout_seconds),
            self._inference_semaphore,
            aclosing(
                engine.stream_generate(
                    model_name=model_name,
                    messages=messages,
                    reason=reason,
                    options=role_options,
                )
            ) as stream,
        ):
            async for token in stream:
                yield token


class RoleInference:
    """绑定角色的生成接口。"""

    def __init__(self, gateway: InferenceGateway, role: str):
        self._gateway = gateway
        self._role = role

    def options(self) -> dict[str, Any]:
        """返回该角色的默认生成参数副本。"""
        return self._gateway._resolve(self._role)[2]

    def context_window(self) -> int:
        """返回该模型在 model-config 中配置的上下文窗口。"""
        return self._gateway._roles[self._role].max_model_len

    async def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return await self._gateway.generate(self._role, messages, **kwargs)

    async def stream(
        self, messages: list[dict[str, str]], **kwargs: Any
    ) -> AsyncGenerator[StreamToken, None]:
        async with aclosing(
            self._gateway.stream(self._role, messages, **kwargs)
        ) as stream:
            async for token in stream:
                yield token
