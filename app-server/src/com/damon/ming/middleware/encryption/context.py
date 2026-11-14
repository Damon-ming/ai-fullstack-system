# app-server/src/com/damon/ming/middleware/encryption/context.py
"""链上共享上下文 —— 贯穿整条 gate 链，承载请求与解密结果。

gate 之间不通过参数传递状态：解密层把会话写进 ctx.session，
响应加密层从 ctx.session 读走。链本身只负责按顺序调用。
"""

from collections.abc import Awaitable, Callable

from fastapi import Request
from src.com.damon.ming.app.encryption.key_management import SessionKey
from src.com.damon.ming.middleware.request_context import (
    EncryptionContext as EncryptionHeaders,
)
from starlette.responses import Response

CallNext = Callable[[Request], Awaitable[Response]]


class EncryptionContext:
    """一次请求在加密链上的共享状态。

    属性：
      request    — 当前请求（gate 从这里读 header / body）
      session    — 解密层写入的会话密钥；响应加密层读取它
      path       — 请求路径（日志 / 白名单判定用）

    便捷取值：
      content_type / enc / session_service / sign_context

    方法：
      call_downstream() — 跳过链上剩余 gate，直接调用下游应用
    """

    def __init__(self, request: Request, downstream: CallNext) -> None:
        self.request = request
        self._downstream = downstream
        self.session: SessionKey | None = None

    # ---- 便捷取值 -----------------------------------------------------

    @property
    def path(self) -> str:
        return self.request.url.path

    @property
    def content_type(self) -> str:
        return self.request.state.ctx.content_type

    @property
    def enc(self) -> EncryptionHeaders:
        """客户端声明的加密协议头（enabled / version / signature_version）。"""
        return self.request.state.encryption

    @property
    def session_service(self):
        """会话服务（解密时按 keyId 取会话密钥）。"""
        return self.request.app.state.encryption.session_service

    @property
    def sign_context(self) -> bytes:
        """签名密钥派生上下文（每套部署独立）。"""
        return self.request.app.state.encryption.sign_context

    # ---- 下游调用 -----------------------------------------------------

    async def call_downstream(self) -> Response:
        """跳过链上剩余 gate，直接调用下游应用。

        用于「本层已决定明文放行」的场景（白名单命中 / debug 开关关闭），
        此时后续的解密与响应加密都不该执行。
        """
        return await self._downstream(self.request)
