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
  X-Signature-Version               → 客户端签名协议版本

错误码（统一 ErrorCode 分段码，详见 exception/error_codes.py）：
  200002003: 客户端加密协议版本不受支持（X-Encrypt-Version header）
  200002004: JSON 解密失败
  200002005: FormData meta 解密失败
  200002006: 会话过期 / 无效
  200002007: 签名验证失败
  200002008: 客户端签名协议版本不受支持（X-Signature-Version header）

版本校验：
  加密版本：客户端必须通过 X-Encrypt-Version header 告知服务端，缺失或不支持返回 200002003。
  签名版本：客户端必须通过 X-Signature-Version header 告知服务端，缺失或不支持返回 200002008。
  两者均在中间件层（不解密即可拒绝）校验。

设计说明：
  本文件位于 middleware/ 而非 encryption/，因为它属于 HTTP 业务逻辑层。
  encryption/ 只负责纯加密原语（AES-GCM、RSA-OAEP、HMAC-SHA256），
  不感知 HTTP 协议。中间件是"用加密能力服务 HTTP 请求"的胶水层。
"""

import json
from collections.abc import Callable

from fastapi import Request
from src.com.damon.ming.encryption.globals import (
    SUPPORTED_ENCRYPTION_VERSIONS,
    SUPPORTED_SIGNATURE_VERSIONS,
    get_key_manager,
    get_sign_context,
)
from src.com.damon.ming.encryption.v1.crypto_engine import (
    AesGcmEngine,
    EncryptedPayload,
)
from src.com.damon.ming.encryption.v1.key_management import KeyManager, SessionKey
from src.com.damon.ming.encryption.v1.signature import (
    derive_signing_key,
    verify_signature,
)
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = pin("middleware.encryption")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _check_version_header(client_version: str) -> str | None:
    """
    检查加密版本是否受支持。

    返回 None 表示通过，否则返回错误消息。
    缺失版本视为不合规，拒绝请求。
    """
    if not client_version:
        return "Missing X-Encrypt-Version header"
    if client_version not in SUPPORTED_ENCRYPTION_VERSIONS:
        return (
            f"Unsupported encryption version: {client_version}, "
            f"supported: {sorted(SUPPORTED_ENCRYPTION_VERSIONS)}"
        )
    return None


def _check_signature_version_header(client_version: str) -> str | None:
    """
    检查签名版本是否受支持。

    返回 None 表示通过，否则返回错误消息。
    缺失版本视为不合规，拒绝请求。
    """
    if not client_version:
        return "Missing X-Signature-Version header"
    if client_version not in SUPPORTED_SIGNATURE_VERSIONS:
        return (
            f"Unsupported signature version: {client_version}, "
            f"supported: {sorted(SUPPORTED_SIGNATURE_VERSIONS)}"
        )
    return None


class EncryptionMiddleware(BaseHTTPMiddleware):
    """透明加密 / 解密 + 签名验证中间件。"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        km = get_key_manager()
        ctx = request.state.ctx
        encrypt_response = ctx.encrypt_enabled
        session: SessionKey | None = None

        # ---- 0. 版本校验（header 层级，不解密即可拒绝）-----------
        version_error = _check_version_header(ctx.encrypt_version)
        if version_error is not None:
            logger.warning(
                "加密版本校验失败: %s | path=%s", version_error, request.url.path
            )
            return JSONResponse(
                status_code=400,
                content={
                    "code": ErrorCode.ENCRYPT.UNSUPPORTED_VERSION,
                    "data": {"error_msg": version_error},
                },
            )

        sig_version_error = _check_signature_version_header(ctx.signature_version)
        if sig_version_error is not None:
            logger.warning(
                "签名版本校验失败: %s | path=%s",
                sig_version_error,
                request.url.path,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "code": ErrorCode.ENCRYPT.UNSUPPORTED_SIGNATURE_VERSION,
                    "data": {"error_msg": sig_version_error},
                },
            )

        content_type = ctx.content_type

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
                                    "code": ErrorCode.ENCRYPT.SESSION_INVALID,
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
                    content={
                        "code": ErrorCode.ENCRYPT.DECRYPTION_FAILED,
                        "data": {"error_msg": "Decryption failed"},
                    },
                )

        # ---- 2. FormData 加密请求：解密 meta + 验证签名 ----------------
        elif "multipart/form-data" in content_type:
            try:
                session = await self._decrypt_and_verify_formdata(request, km)
                if session is None:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "code": ErrorCode.ENCRYPT.SESSION_INVALID,
                            "data": {"error_msg": "Invalid session or bad signature"},
                        },
                    )
                encrypt_response = True
            except Exception as e:
                logger.warning("FormData 解密失败: %s", e)
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": ErrorCode.ENCRYPT.META_DECRYPT_FAILED,
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

        # 验证签名（业务层约定：signature/timestamp/nonce 不参与签名）
        # 签名密钥从会话 AES 密钥派生（每个会话独立）
        signing_key = derive_signing_key(session.aes_key, get_sign_context())
        sig_ok, sig_reason = verify_signature(
            params=decrypted_json,
            secret=signing_key.hex(),
            signature=decrypted_json.get("signature", ""),
            timestamp=decrypted_json.get("timestamp", 0),
            nonce=decrypted_json.get("nonce", ""),
            exclude_keys={"signature", "timestamp", "nonce"},
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

        # 验证签名（业务层约定：signature/timestamp/nonce 不参与签名）
        # 签名密钥从会话 AES 密钥派生（每个会话独立）
        signing_key = derive_signing_key(session.aes_key, get_sign_context())
        sig_ok, sig_reason = verify_signature(
            params=meta,
            secret=signing_key.hex(),
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
            exclude_keys={"signature", "timestamp", "nonce"},
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
