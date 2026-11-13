# app-server/src/com/damon/ming/middleware/encryption_middleware.py
"""
FastAPI 加密 + 签名中间件（薄适配器）。

本文件只负责把 Starlette 的 (request, call_next) 接入加密处理链，
所有处理逻辑都在 middleware/encryption/ 包内，按链式 gate 组装。

职责（对上层路由透明）：
  - 拦截请求体：
    * JSON 加密格式 → 解密 → 验证签名
    * FormData → 解密 meta_json_encrypted → 验证签名 → 还原 meta_json
  - 拦截响应体：加密后再发回客户端
    * JSON → 整体加密
    * SSE（text/event-stream）→ 逐事件加密 data 字段

协议：
  JSON:    加密 body = { "encrypted", "nonce", "keyId" }
  FormData: meta_json_encrypted = { "encrypted", "nonce", "keyId" }
           + form fields: timestamp, nonce, signature

签名头：
  X-Timestamp, X-Nonce, X-Signature  → 或从 FormData 字段读取
  X-Signature-Version               → 客户端签名协议版本

开关与白名单（服务端主导，客户端不再自行决定）：
  命中白名单前缀的路径 → 明文放行（不解密、不加密响应）
  白名单来自 app.state.config.system_config.whitelist（系统配置，
  环境无关的 HTTP 路由策略；不放在 encryption-config.yaml）
  未命中白名单时按 X-Encrypt-Enabled 头 + 运行环境决定：
    debug  ：客户端未声明加密 → 明文放行（前端可调试开关）
    release：客户端未声明加密 → 400（必须加密，fail-closed）
  声明加密后，版本头与加密体缺一不可，否则 400。

错误码（统一 ErrorCode 分段码，详见 exception/error_codes.py）：
  200002003: 客户端加密协议版本不受支持（X-Encrypt-Version header）
  200002004: JSON 解密失败
  200002005: FormData meta 解密失败
  200002006: 会话过期 / 无效
  200002007: 签名验证失败
  200002008: 客户端签名协议版本不受支持（X-Signature-Version header）
  200002009: 请求重放拦截（nonce 已使用过）
  200002010: 空 nonce 拒绝（加密请求必须携带非空 nonce）
  200002011: 当前环境要求加密，请求未按加密协议发送
  200002012: 响应加密失败（安全关键路径，拒绝返回明文）

版本校验：
  加密版本：客户端必须通过 X-Encrypt-Version header 告知服务端，缺失或不支持返回 200002003。
  签名版本：客户端必须通过 X-Signature-Version header 告知服务端，缺失或不支持返回 200002008。
  两者均在中间件层（不解密即可拒绝）校验。

设计说明：
  本文件位于 middleware/ 而非 encryption/，因为它属于 HTTP 业务逻辑层。
  encryption/ 只负责纯加密原语（AES-GCM、RSA-OAEP、HMAC-SHA256），
  不感知 HTTP 协议。中间件是"用加密能力服务 HTTP 请求"的胶水层。
"""

from collections.abc import Callable

from fastapi import Request
from src.com.damon.ming.middleware.encryption import build_encryption_chain
from src.com.damon.ming.middleware.encryption.chain import EncryptionChain
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp


class EncryptionMiddleware(BaseHTTPMiddleware):
    """透明加密 / 解密 + 签名验证中间件。"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._chain: EncryptionChain = build_encryption_chain()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        return await self._chain.run(request, call_next)
