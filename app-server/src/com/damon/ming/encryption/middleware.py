# app-server/src/com/damon/ming/encryption/middleware.py
"""
FastAPI 加密中间件

职责（对上层路由透明）：
  - 拦截请求体，如果 body 是加密格式则解密后再传给路由
  - 拦截响应体，加密后再发回客户端

协议：
  加密 body = { "encrypted": base64, "nonce": base64, "keyId": string }
  请求头 X-Encrypt-Enabled: 1  → 服务端对响应也加密返回

注意：
  SSE 流式响应不在本中间件处理范围内（流式数据量小且实时性要求高），
  流式接口如需加密需在 SSE 协议层另行处理。
"""

import json
from collections.abc import Callable

from fastapi import Request
from src.com.damon.ming.encryption.crypto_engine import AesGcmEngine, EncryptedPayload
from src.com.damon.ming.encryption.key_management import KeyManager, SessionKey
from src.com.damon.ming.log import pin
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = pin("encryption.middleware")

# 全局 KeyManager 实例（在 lifespan 中初始化）
_key_manager: KeyManager | None = None


def get_key_manager() -> KeyManager:
    if _key_manager is None:
        raise RuntimeError(
            "KeyManager not initialized. Ensure lifespan calls initialize."
        )
    return _key_manager


def set_key_manager(km: KeyManager) -> None:
    global _key_manager
    _key_manager = km


# ---------------------------------------------------------------------------
# 中间件
# ---------------------------------------------------------------------------


class EncryptionMiddleware(BaseHTTPMiddleware):
    """
    透明加密 / 解密中间件。对路由 handler 完全透明。
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        km = get_key_manager()

        # 客户端是否期望加密响应（首次 key exchange 请求为 false）
        encrypt_response = request.headers.get("x-encrypt-enabled") == "1"
        session: SessionKey | None = None

        # ---- 1. 尝试解密请求体 -------------------------------------------
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                raw_body = await request.body()
                if raw_body:
                    body_json = json.loads(raw_body)
                    if _is_encrypted_body(body_json):
                        session = km.get_session(body_json.get("keyId", ""))
                        if session is None:
                            logger.warning(
                                "无效或过期的加密会话 | key_id=%s",
                                body_json.get("keyId"),
                            )
                            return JSONResponse(
                                status_code=401,
                                content={
                                    "code": 40101,
                                    "data": {"error_msg": "Invalid or expired session"},
                                },
                            )

                        decrypted_str = AesGcmEngine.decrypt_payload(
                            EncryptedPayload(
                                encrypted=body_json["encrypted"],
                                nonce=body_json["nonce"],
                                key_id=body_json["keyId"],
                            ),
                            session.aes_key,
                        )

                        # 用解密后的明文替换 request.body() 的返回值
                        _patch_request_body(request, decrypted_str)
                        request.state.enc_session = session
                        encrypt_response = True
                        logger.debug("请求已解密 | key_id=%s", session.key_id)
            except Exception as e:
                logger.warning("请求解密失败: %s", e)
                return JSONResponse(
                    status_code=400,
                    content={"code": 40001, "data": {"error_msg": "Decryption failed"}},
                )

        # ---- 2. 调用下游路由 --------------------------------------------
        response = await call_next(request)

        # ---- 3. 加密响应 ------------------------------------------------
        if encrypt_response and _is_json_response(response):
            try:
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk

                body_json = json.loads(response_body)
                # 优先使用本次请求解密时找到的 session
                active_session = session or getattr(request.state, "enc_session", None)
                if active_session is None:
                    # 异常路径：客户端声明加密但无法找到会话，原样返回
                    return Response(
                        content=response_body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )

                encrypted_payload = AesGcmEngine.encrypt_json(
                    json.dumps(body_json, ensure_ascii=False),
                    active_session.aes_key,
                    active_session.key_id,
                )
                return JSONResponse(content=encrypted_payload.to_dict())
            except Exception as e:
                logger.warning("响应加密失败: %s", e)
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

        return response


# ---------------------------------------------------------------------------
# 私有辅助
# ---------------------------------------------------------------------------


def _is_encrypted_body(body: dict) -> bool:
    """判断 body 是否为加密格式。"""
    return (
        isinstance(body, dict)
        and isinstance(body.get("encrypted"), str)
        and isinstance(body.get("nonce"), str)
        and isinstance(body.get("keyId"), str)
    )


def _is_json_response(response: Response) -> bool:
    return response.media_type == "application/json"


def _patch_request_body(request: Request, new_body: str) -> None:
    """
    替换 Starlette Request 的 body() 返回值。

    Starlette 的 Request.body() 内部读取 stream 并缓存到 _body，
    我们直接覆盖 _body 并替换 body() 方法，使下游路由能透明读取明文。
    """
    body_bytes = new_body.encode("utf-8")
    request._body = body_bytes

    # 替换 body() 方法，直接返回缓存的明文
    async def _new_body() -> bytes:
        return body_bytes

    request.body = _new_body  # type: ignore[method-assign]
