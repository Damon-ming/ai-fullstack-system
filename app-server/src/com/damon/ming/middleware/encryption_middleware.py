# app-server/src/com/damon/ming/middleware/encryption_middleware.py
"""
加密中间件 —— inbound（白名单/解密）+ outbound（响应加密）。

职责：
  inbound:
    - 白名单判定（明文放行）
    - 开关判定（debug/release 策略）
    - 版本校验
    - 解密 + 验签
    - 会话密钥写入链上上下文（供本 middleware outbound 读取）
  outbound:
    - 响应加密（JSON / SSE）

协议：见下方错误码

错误码：
  200002003/200002008: 版本不受支持
  200002004/200002005: 解密失败
  200002006: 会话过期
  200002007: 签名验证失败
  200002009: 重放拦截
  200002010: 空 nonce
  200002011: 加密开关
  200002012: 响应加密失败
"""

from collections.abc import Callable

from fastapi import Request
from src.com.damon.ming.middleware.encryption import build_encryption_chain
from src.com.damon.ming.middleware.encryption.chain import EncryptionChain
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp


class EncryptionMiddleware(BaseHTTPMiddleware):
    """加密中间件 —— inbound + outbound 一体。"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._chain: EncryptionChain = build_encryption_chain()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        return await self._chain.run(request, call_next)
