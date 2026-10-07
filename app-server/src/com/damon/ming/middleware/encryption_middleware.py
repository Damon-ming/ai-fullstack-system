# app-server/src/com/damon/ming/middleware/encryption_middleware.py
"""
FastAPI 加密 + 签名中间件

职责（对上层路由透明）：
  - 拦截请求体：
    * JSON 加密格式 → 解密 → 验证签名
    * FormData → 解密 meta_json_encrypted → 验证签名 → 还原 meta_json
  - 拦截响应体：加密后再发回客户端

协议：
  JSON:    加密 body = { "encrypted", "nonce", "keyId" }
  FormData: meta_json_encrypted = { "encrypted", "nonce", "keyId" }
           + form fields: timestamp, nonce, signature

签名头：
  X-Timestamp, X-Nonce, X-Signature  → 或从 FormData 字段读取

错误码：
  40001: JSON 解密失败
  40002: FormData meta 解密失败
  40101: 会话过期 / 无效
  40102: 签名验证失败

设计说明：
  本文件位于 middleware/ 而非 encryption/，因为它属于 HTTP 业务逻辑层。
  encryption/ 只负责纯加密原语（AES-GCM、RSA-OAEP、HMAC-SHA256），
  不感知 HTTP 协议。中间件是"用加密能力服务 HTTP 请求"的胶水层。
"""

import json
from collections.abc import Callable

from fastapi import Request
from src.com.damon.ming.encryption.crypto_engine import AesGcmEngine, EncryptedPayload
from src.com.damon.ming.encryption.globals import (
    get_key_manager,
    get_signature_secret,
)
from src.com.damon.ming.encryption.key_management import KeyManager, SessionKey
from src.com.damon.ming.encryption.signature import verify_signature
from src.com.damon.ming.log import pin
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = pin("middleware.encryption")


class EncryptionMiddleware(BaseHTTPMiddleware):
    """透明加密 / 解密 + 签名验证中间件。"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        km = get_key_manager()
        encrypt_response = request.headers.get("x-encrypt-enabled") == "1"
        session: SessionKey | None = None

        content_type = request.headers.get("content-type", "")

        # ---- 1. JSON 加密请求：解密 + 验证签名 -----------------------
        if "application/json" in content_type:
            try:
                raw_body = await request.body()
                if raw_body:
                    body_json = json.loads(raw_body)
                    if _is_encrypted_body(body_json):
                        session = await self._decrypt_and_verify_json(
                            request, km, body_json
                        )
                        if session is None:
                            return JSONResponse(
                                status_code=401,
                                content={
                                    "code": 40101,
                                    "data": {
                                        "error_msg": "Invalid session or bad signature"
                                    },
                                },
                            )
                        encrypt_response = True
            except Exception as e:
                logger.warning("JSON 解密失败: %s", e)
                return JSONResponse(
                    status_code=400,
                    content={"code": 40001, "data": {"error_msg": "Decryption failed"}},
                )

        # ---- 2. FormData 加密请求：解密 meta + 验证签名 ----------------
        elif "multipart/form-data" in content_type:
            try:
                session = await self._decrypt_and_verify_formdata(request, km)
                if session is None:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "code": 40101,
                            "data": {"error_msg": "Invalid session or bad signature"},
                        },
                    )
                encrypt_response = True
            except Exception as e:
                logger.warning("FormData 解密失败: %s", e)
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": 40002,
                        "data": {"error_msg": "Meta decryption failed"},
                    },
                )

        # ---- 3. 调用下游 --------------------------------------------
        response = await call_next(request)

        # ---- 4. 加密响应 --------------------------------------------
        if encrypt_response and _is_json_response(response):
            return await self._encrypt_response(request, response, km, session)

        return response

    # ==== 私有 ============================================================

    async def _decrypt_and_verify_json(
        self, request: Request, km: KeyManager, body_json: dict
    ) -> SessionKey | None:
        """解密 JSON 请求并验证签名。返回 session 或 None。"""
        session = km.get_session(body_json.get("keyId", ""))
        if session is None:
            return None

        decrypted_str = AesGcmEngine.decrypt_payload(
            EncryptedPayload(
                encrypted=body_json["encrypted"],
                nonce=body_json["nonce"],
                key_id=body_json["keyId"],
            ),
            session.aes_key,
        )
        decrypted_json = json.loads(decrypted_str)

        # 验证签名
        sig_ok, sig_reason = verify_signature(
            params=decrypted_json,
            secret=get_signature_secret(),
            signature=decrypted_json.get("signature", ""),
            timestamp=decrypted_json.get("timestamp", 0),
            nonce=decrypted_json.get("nonce", ""),
        )
        if not sig_ok:
            logger.warning("JSON 签名验证失败: %s", sig_reason)
            return None

        _patch_request_body(request, decrypted_str)
        request.state.enc_session = session
        logger.debug("JSON 请求已解密并验证签名 | key_id=%s", session.key_id)
        return session

    async def _decrypt_and_verify_formdata(
        self, request: Request, km: KeyManager
    ) -> SessionKey | None:
        """解密 FormData 的 meta_json_encrypted 并验证签名。"""
        form = await request.form()
        meta_encrypted_str = form.get("meta_json_encrypted")
        timestamp = int(form.get("timestamp", 0))
        nonce = form.get("nonce", "")
        signature = form.get("signature", "")

        if not meta_encrypted_str:
            return None

        meta_encrypted = json.loads(meta_encrypted_str)
        if not _is_encrypted_body(meta_encrypted):
            return None

        session = km.get_session(meta_encrypted.get("keyId", ""))
        if session is None:
            return None

        meta_str = AesGcmEngine.decrypt_payload(
            EncryptedPayload(
                encrypted=meta_encrypted["encrypted"],
                nonce=meta_encrypted["nonce"],
                key_id=meta_encrypted["keyId"],
            ),
            session.aes_key,
        )
        meta = json.loads(meta_str)

        # 验证签名
        sig_ok, sig_reason = verify_signature(
            params=meta,
            secret=get_signature_secret(),
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )
        if not sig_ok:
            logger.warning("FormData 签名验证失败: %s", sig_reason)
            return None

        # 将解密后的 meta 注入 request.state，供路由读取
        request.state.decrypted_meta = meta
        request.state.enc_session = session
        logger.debug("FormData 已解密并验证签名 | key_id=%s", session.key_id)
        return session

    async def _encrypt_response(
        self,
        request: Request,
        response: Response,
        km: KeyManager,
        session: SessionKey | None,
    ) -> Response:
        """加密 JSON 响应。"""
        try:
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            body_json = json.loads(response_body)
            active_session = session or getattr(request.state, "enc_session", None)
            if active_session is None:
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


def _is_encrypted_body(body: dict) -> bool:
    return (
        isinstance(body, dict)
        and isinstance(body.get("encrypted"), str)
        and isinstance(body.get("nonce"), str)
        and isinstance(body.get("keyId"), str)
    )


def _is_json_response(response: Response) -> bool:
    return response.media_type == "application/json"


def _patch_request_body(request: Request, new_body: str) -> None:
    body_bytes = new_body.encode("utf-8")
    request._body = body_bytes

    async def _new_body() -> bytes:
        return body_bytes

    request.body = _new_body  # type: ignore[method-assign]
