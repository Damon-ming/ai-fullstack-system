"""按业务 role 路由到已装配的推理引擎。"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any

from src.com.damon.ming.ai.infer.base_inference import BaseInferenceService, StreamToken


class InferenceGateway:
    """统一推理入口。引擎由启动配置装配；调用方只需声明 role。"""

    def __init__(
        self,
        roles: dict[str, Any],
        inference_semaphore: asyncio.Semaphore | None = None,
    ):
        if not roles:
            raise ValueError("InferenceGateway 至少需要一个已配置 role")
        self._roles = dict(roles)
        self._inference_semaphore = inference_semaphore

    def get(self, role: str) -> "RoleInference":
        """获取指定角色的推理入口。"""
        self._resolve(role)
        return RoleInference(self, role)

    def _resolve(self, role: str) -> tuple[BaseInferenceService, str, dict[str, Any]]:
        try:
            entry = self._roles[role]
        except KeyError as exc:
            raise ValueError(f"未配置推理 role: {role}") from exc
        return entry.engine, entry.model_name, dict(entry.options)

    def role_options(self, role: str) -> dict[str, Any]:
        """返回角色默认参数副本，供上层计算预算时读取。"""
        return dict(self._resolve(role)[2])

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

        if role in ("inference", "summary") and self._inference_semaphore is not None:
            async with self._inference_semaphore:
                return await call()
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

        async def produce() -> AsyncGenerator[StreamToken, None]:
            async with aclosing(
                engine.stream_generate(
                    model_name=model_name,
                    messages=messages,
                    reason=reason,
                    options=role_options,
                )
            ) as stream:
                async for token in stream:
                    yield token

        async with aclosing(produce()) as stream:
            if (
                role in ("inference", "summary")
                and self._inference_semaphore is not None
            ):
                async with self._inference_semaphore:
                    async for token in stream:
                        yield token
            else:
                async for token in stream:
                    yield token


class RoleInference:
    """绑定角色的生成接口。"""

    def __init__(self, gateway: InferenceGateway, role: str):
        self._gateway = gateway
        self._role = role

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
