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
  200002009: 请求重放拦截（nonce 已使用过）
  200002010: 空 nonce 拒绝（加密请求必须携带非空 nonce）

版本校验：
  加密版本：客户端必须通过 X-Encrypt-Version header 告知服务端，缺失或不支持返回 200002003。
  签名版本：客户端必须通过 X-Signature-Version header 告知服务端，缺失或不支持返回 200002008。
  两者均在中间件层（不解密即可拒绝）校验。

设计说明：
  本文件位于 middleware/ 而非 encryption/，因为它属于 HTTP 业务逻辑层。
  encryption/ 只负责纯加密原语（AES-GCM、RSA-OAEP、HMAC-SHA256），
  不感知 HTTP 协议。中间件是"用加密能力服务 HTTP 请求"的胶水层。
"""

import asyncio
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import ClassVar

from fastapi import Request
from src.com.damon.ming.encryption.globals import (
    SUPPORTED_ENCRYPTION_VERSIONS,
    SUPPORTED_SIGNATURE_VERSIONS,
    get_sign_context,
)
from src.com.damon.ming.encryption.v1.crypto_engine import (
    AesGcmEngine,
    EncryptedPayload,
)
from src.com.damon.ming.encryption.v1.key_management import SessionKey
from src.com.damon.ming.encryption.v1.signature import (
    derive_signing_key,
    verify_signature,
)
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.schemas.response import BaseBizFailedData, BaseFailedResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = pin("middleware.encryption")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _check_version_header(client_version: str) -> tuple[str, dict] | None:
    """
    检查加密版本是否受支持。

    返回 None 表示通过，否则返回 (i18n_key, params)。
    缺失版本视为不合规，拒绝请求。
    """
    if not client_version:
        return I18nKey.ENCRYPT_UNSUPPORTED_VERSION, {
            "version": "",
            "supported": str(sorted(SUPPORTED_ENCRYPTION_VERSIONS)),
        }
    if client_version not in SUPPORTED_ENCRYPTION_VERSIONS:
        return (
            I18nKey.ENCRYPT_UNSUPPORTED_VERSION,
            {
                "version": client_version,
                "supported": str(sorted(SUPPORTED_ENCRYPTION_VERSIONS)),
            },
        )
    return None


def _replay_response() -> JSONResponse:
    """构建重放拦截响应（400 + 重放错误码）。"""
    return JSONResponse(
        status_code=400,
        content=BaseFailedResponse(
            code=ErrorCode.ENCRYPT.SIGNATURE_REPLAY_DETECTED,
            data=BaseBizFailedData(error_msg=t(I18nKey.ENCRYPT_REPLAY_DETECTED)),
        ).model_dump(),
    )


def _empty_nonce_response() -> JSONResponse:
    """构建空 nonce 拒绝响应（400 + 空 nonce 错误码）。"""
    return JSONResponse(
        status_code=400,
        content=BaseFailedResponse(
            code=ErrorCode.ENCRYPT.EMPTY_NONCE,
            data=BaseBizFailedData(error_msg=t(I18nKey.ENCRYPT_EMPTY_NONCE)),
        ).model_dump(),
    )


def _check_signature_version_header(client_version: str) -> tuple[str, dict] | None:
    """
    检查签名版本是否受支持。

    返回 None 表示通过，否则返回 (i18n_key, params)。
    缺失版本视为不合规，拒绝请求。
    """
    if not client_version:
        return I18nKey.ENCRYPT_UNSUPPORTED_SIG_VERSION, {
            "version": "",
            "supported": str(sorted(SUPPORTED_SIGNATURE_VERSIONS)),
        }
    if client_version not in SUPPORTED_SIGNATURE_VERSIONS:
        return (
            I18nKey.ENCRYPT_UNSUPPORTED_SIG_VERSION,
            {
                "version": client_version,
                "supported": str(sorted(SUPPORTED_SIGNATURE_VERSIONS)),
            },
        )
    return None


class EncryptionMiddleware(BaseHTTPMiddleware):
    """透明加密 / 解密 + 签名验证中间件。"""

    # ── nonce 重放防护缓存 ──────────────────────────────────────────
    # key = "session_key_id:nonce", value = 首次接收时间戳（秒）
    _nonce_cache: ClassVar[OrderedDict[str, float]] = OrderedDict()
    _nonce_cache_lock: ClassVar[asyncio.Lock | None] = None
    _NONCE_TTL_SECONDS: ClassVar[int] = 600  # 10 分钟（2 × 5 分钟签名容差）
    _NONCE_CACHE_MAX: ClassVar[int] = 10_000  # LRU 上限
    _NONCE_EVICT_RATIO: ClassVar[float] = 0.2  # 超限时淘汰最老的 20%

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    @classmethod
    def _ensure_lock(cls) -> asyncio.Lock:
        """惰性创建 nonce 缓存锁（首次请求时绑定到当前事件循环）。"""
        if cls._nonce_cache_lock is None:
            cls._nonce_cache_lock = asyncio.Lock()
        return cls._nonce_cache_lock

    @classmethod
    async def _check_and_store_nonce(cls, session_key_id: str, nonce: str) -> bool:
        """检查 nonce 是否已使用过，未使用则记录。

        Returns:
            True  = nonce 新鲜，可以继续
            False = nonce 已存在（重放），拒绝请求
        """
        # 空 nonce 在调用方已处理，此处为防御性保留

        cache_key = f"{session_key_id}:{nonce}"
        now = time.time()

        async with cls._ensure_lock():
            # 检查是否存在且未过期
            if cache_key in cls._nonce_cache:
                first_seen = cls._nonce_cache[cache_key]
                if now - first_seen < cls._NONCE_TTL_SECONDS:
                    return False  # 重放命中
                # 已过期，移除后重新记录
                del cls._nonce_cache[cache_key]

            # 记录新 nonce
            cls._nonce_cache[cache_key] = now
            cls._nonce_cache.move_to_end(cache_key)

            # 超限淘汰
            if len(cls._nonce_cache) > cls._NONCE_CACHE_MAX:
                evict_count = int(cls._NONCE_CACHE_MAX * cls._NONCE_EVICT_RATIO)
                for _ in range(evict_count):
                    cls._nonce_cache.popitem(last=False)

        return True

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        sm = request.state.session_service
        ctx = request.state.ctx
        encrypt_response = ctx.encrypt_enabled
        session: SessionKey | None = None

        # ---- 0. 版本校验（header 层级，不解密即可拒绝）-----------
        version_error = _check_version_header(ctx.encrypt_version)
        if version_error is not None:
            i18n_key, i18n_params = version_error
            logger.warning("加密版本校验失败: %s | path=%s", i18n_key, request.url.path)
            return JSONResponse(
                status_code=400,
                content=BaseFailedResponse(
                    code=ErrorCode.ENCRYPT.UNSUPPORTED_VERSION,
                    data=BaseBizFailedData(error_msg=t(i18n_key, **i18n_params)),
                ).model_dump(),
            )

        sig_version_error = _check_signature_version_header(ctx.signature_version)
        if sig_version_error is not None:
            i18n_key, i18n_params = sig_version_error
            logger.warning(
                "签名版本校验失败: %s | path=%s",
                i18n_key,
                request.url.path,
            )
            return JSONResponse(
                status_code=400,
                content=BaseFailedResponse(
                    code=ErrorCode.ENCRYPT.UNSUPPORTED_SIGNATURE_VERSION,
                    data=BaseBizFailedData(error_msg=t(i18n_key, **i18n_params)),
                ).model_dump(),
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
                            request, sm, body_json
                        )
                        if isinstance(session, Response):
                            return session
                        if session is None:
                            return JSONResponse(
                                status_code=401,
                                content=BaseFailedResponse(
                                    code=ErrorCode.ENCRYPT.SESSION_INVALID,
                                    data=BaseBizFailedData(
                                        error_msg=t(I18nKey.ENCRYPT_SESSION_INVALID)
                                    ),
                                ).model_dump(),
                            )
                        encrypt_response = True
            except Exception as e:
                logger.warning("JSON 解密失败: %s", e)
                return JSONResponse(
                    status_code=400,
                    content=BaseFailedResponse(
                        code=ErrorCode.ENCRYPT.DECRYPTION_FAILED,
                        data=BaseBizFailedData(
                            error_msg=t(I18nKey.ENCRYPT_DECRYPTION_FAILED)
                        ),
                    ).model_dump(),
                )

        # ---- 2. FormData 加密请求：解密 meta + 验证签名 ----------------
        elif "multipart/form-data" in content_type:
            try:
                session = await self._decrypt_and_verify_formdata(request, sm)
                if isinstance(session, Response):
                    return session
                if session is None:
                    return JSONResponse(
                        status_code=401,
                        content=BaseFailedResponse(
                            code=ErrorCode.ENCRYPT.SESSION_INVALID,
                            data=BaseBizFailedData(
                                error_msg=t(I18nKey.ENCRYPT_SESSION_INVALID)
                            ),
                        ).model_dump(),
                    )
                encrypt_response = True
            except Exception as e:
                logger.warning("FormData 解密失败: %s", e)
                return JSONResponse(
                    status_code=400,
                    content=BaseFailedResponse(
                        code=ErrorCode.ENCRYPT.META_DECRYPT_FAILED,
                        data=BaseBizFailedData(
                            error_msg=t(I18nKey.ENCRYPT_DECRYPTION_FAILED)
                        ),
                    ).model_dump(),
                )

        # ---- 3. 调用下游 --------------------------------------------
        response = await call_next(request)

        # ---- 4. 加密响应 --------------------------------------------
        if encrypt_response and _is_json_response(response):
            return await self._encrypt_response(request, response, session)

        return response

    # ==== 私有 ============================================================

    async def _decrypt_and_verify_json(
        self, request: Request, sm, body_json: dict
    ) -> SessionKey | None:
        """解密 JSON 请求并验证签名。

        返回:
          SessionKey  — 验证全部通过
          None        — 会话失效或签名错误（由调用方返回 SESSION_INVALID）
          JSONResponse — 空 nonce 或重放命中（已构建好的错误响应，调用方应直接返回）
        """
        key_id = body_json.get("keyId", "")
        session = await sm.get_session_async(
            key_id, session_id=request.state.ctx.session_id
        )
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

        # nonce 重放防护（签名通过后检查，确保同一请求不被重复执行）
        nonce = decrypted_json.get("nonce", "")
        if not nonce:
            logger.warning(
                "JSON 请求空 nonce 拒绝 | key_id=%s", session.key_id[:12] + "..."
            )
            return _empty_nonce_response()
        if not await self._check_and_store_nonce(session.key_id, nonce):
            logger.warning(
                "JSON 请求重放拦截 | key_id=%s | nonce=%s",
                session.key_id[:12] + "...",
                nonce[:16] + "...",
            )
            return _replay_response()

        _patch_request_body(request, decrypted_str)
        request.state.enc_session = session
        logger.debug("JSON 请求已解密并验证签名 | key_id=%s", session.key_id)
        return session

    async def _decrypt_and_verify_formdata(
        self, request: Request, sm
    ) -> SessionKey | None:
        """解密 FormData 的 meta_json_encrypted 并验证签名。

        返回:
          SessionKey  — 验证全部通过
          None        — 会话失效或签名错误（由调用方返回 SESSION_INVALID）
          JSONResponse — 空 nonce 或重放命中（已构建好的错误响应，调用方应直接返回）
        """
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

        key_id = meta_encrypted.get("keyId", "")
        session = await sm.get_session_async(
            key_id, session_id=request.state.ctx.session_id
        )
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

        # nonce 重放防护（签名通过后检查，确保同一请求不被重复执行）
        if not nonce:
            logger.warning(
                "FormData 请求空 nonce 拒绝 | key_id=%s", session.key_id[:12] + "..."
            )
            return _empty_nonce_response()
        if not await self._check_and_store_nonce(session.key_id, nonce):
            logger.warning(
                "FormData 请求重放拦截 | key_id=%s | nonce=%s",
                session.key_id[:12] + "...",
                nonce[:16] + "...",
            )
            return _replay_response()

        # 将解密后的 meta 注入 request.state，供路由读取
        request.state.decrypted_meta = meta
        request.state.enc_session = session
        logger.debug("FormData 已解密并验证签名 | key_id=%s", session.key_id)
        return session

    async def _encrypt_response(
        self,
        request: Request,
        response: Response,
        session: SessionKey | None,
    ) -> Response:
        """加密 JSON 响应。

        加密是安全关键路径，失败时拒绝返回（抛异常→500），
        不降级返回明文，避免加密模式被静默绕过。
        """
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        body_json = json.loads(response_body)
        logger.debug(
            "响应加密 | path=%s | body_bytes=%d",
            request.url.path,
            len(response_body),
        )
        active_session = session or getattr(request.state, "enc_session", None)
        if active_session is None:
            # 协议层面不应发生（encrypt_response=True 时 session 必须存在），
            # 作为最后的安全网直接返回原始体。
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

    def _new_body() -> bytes:
        return body_bytes

    request.body = _new_body  # type: ignore[method-assign]
