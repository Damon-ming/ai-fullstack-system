"""按业务 role 路由到已装配的推理引擎。"""

from collections.abc import AsyncGenerator
from typing import Any

from src.com.damon.ming.ai.infer.base_inference import BaseInferenceService, StreamToken


class InferenceGateway:
    """统一推理入口。引擎由启动配置装配；调用方只需声明 role。"""

    def __init__(self, roles: dict[str, Any]):
        if not roles:
            raise ValueError("InferenceGateway 至少需要一个已配置 role")
        self._roles = dict(roles)

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
        return await engine.text_generation(
            model_name=model_name,
            messages=messages,
            reason=reason,
            response_schema=response_schema,
            options=role_options,
        )

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
        async for token in engine.stream_generate(
            model_name=model_name,
            messages=messages,
            reason=reason,
            options=role_options,
        ):
            yield token
