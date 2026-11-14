# app-server/src/com/damon/ming/middleware/encryption/decrypt.py
"""请求解密策略（inbound）—— 一种 content-type 对应一个策略。

策略是平级的：由 DecryptGate 持有，按顺序取第一个 supports() 命中的。
解密成功后策略返回 None（会话已写入 ctx.session），由 gate 继续走后面的
响应加密层；失败返回拒绝响应。
"""

import json
from abc import ABC, abstractmethod

from src.com.damon.ming.app.encryption.key_management import DecryptedSessionKey
from src.com.damon.ming.encryption.constants import (
    SIGNATURE_TIMESTAMP_TOLERANCE_MS,
)
from src.com.damon.ming.encryption.v1.crypto_engine import (
    AesGcmEngine,
    EncryptedPayload,
)
from src.com.damon.ming.encryption.v1.signature import (
    derive_signing_key,
    verify_signature,
)
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.encryption.context import EncryptionContext
from src.com.damon.ming.middleware.encryption.nonce import NonceCache
from src.com.damon.ming.middleware.encryption.responses import (
    decryption_failed_response,
    empty_nonce_response,
    encryption_required_response,
    meta_decryption_failed_response,
    replay_response,
    session_invalid_response,
)
from src.com.damon.ming.middleware.encryption.wire import (
    is_encrypted_body,
    patch_request_body,
)
from starlette.responses import Response

logger = pin("middleware.encryption")

# 业务层约定：这三个字段不参与签名
_EXCLUDED_FROM_SIGNATURE = {"signature", "timestamp", "nonce"}


def _key_id_preview(session: DecryptedSessionKey) -> str:
    """日志用的 keyId 摘要（避免完整 keyId 落日志）。"""
    return session.key_id[:12] + "..."


class DecryptStrategy(ABC):
    """解密策略：一种 content-type 对应一个策略。

    supports() 判断本策略是否适用于当前请求；apply() 执行解密，
    成功返回 None（会话已写入 ctx.session），失败返回拒绝响应。
    """

    def __init__(self, nonce_cache: NonceCache) -> None:
        self._nonce_cache = nonce_cache

    @abstractmethod
    def supports(self, ctx: EncryptionContext) -> bool:
        """是否由本策略处理该请求。"""
        raise NotImplementedError

    @abstractmethod
    async def apply(self, ctx: EncryptionContext) -> Response | None:
        """解密 + 验签。None = 成功；Response = 拒绝。"""
        raise NotImplementedError


class JsonDecryptStrategy(DecryptStrategy):
    """application/json：body 整体为加密信封。"""

    def supports(self, ctx: EncryptionContext) -> bool:
        return "application/json" in ctx.content_type

    async def apply(self, ctx: EncryptionContext) -> Response | None:
        request = ctx.request
        path = ctx.path
        try:
            raw_body = await request.body()
            if not raw_body:
                logger.warning("加密请求体为空 | path=%s", path)
                return encryption_required_response()

            body_json = json.loads(raw_body)
            if not is_encrypted_body(body_json):
                logger.warning("请求体未按加密协议发送 | path=%s", path)
                return encryption_required_response()

            session = await ctx.session_service.get_session(
                body_json.get("keyId", ""),
                session_id=request.state.client.session_id,
            )
            if session is None:
                return session_invalid_response()

            decrypted_str = AesGcmEngine.decrypt_payload(
                EncryptedPayload(
                    encrypted=body_json["encrypted"],
                    nonce=body_json["nonce"],
                    key_id=body_json["keyId"],
                ),
                session.aes_key,
            )
            decrypted_json = json.loads(decrypted_str)

            # 签名密钥从会话 AES 密钥派生（每个会话独立）
            signing_key = derive_signing_key(session.aes_key, ctx.sign_context)
            sig_ok, sig_reason = verify_signature(
                params=decrypted_json,
                secret=signing_key.hex(),
                signature=decrypted_json.get("signature", ""),
                timestamp=decrypted_json.get("timestamp", 0),
                nonce=decrypted_json.get("nonce", ""),
                exclude_keys=_EXCLUDED_FROM_SIGNATURE,
                timestamp_tolerance_ms=SIGNATURE_TIMESTAMP_TOLERANCE_MS,
            )
            if not sig_ok:
                logger.warning("JSON 签名验证失败: %s", sig_reason)
                return session_invalid_response()

            # nonce 重放防护（签名通过后检查，确保同一请求不被重复执行）
            nonce = decrypted_json.get("nonce", "")
            if not nonce:
                logger.warning(
                    "JSON 请求空 nonce 拒绝 | key_id=%s", _key_id_preview(session)
                )
                return empty_nonce_response()
            if not await self._nonce_cache.check_and_store(session.key_id, nonce):
                logger.warning(
                    "JSON 请求重放拦截 | key_id=%s | nonce=%s",
                    _key_id_preview(session),
                    nonce[:16] + "...",
                )
                return replay_response()

            patch_request_body(request, decrypted_str)
            request.state.enc_session = session
            ctx.session = session
            logger.debug(
                "JSON 请求已解密并验证签名 | key_id=%s", _key_id_preview(session)
            )
            return None
        except Exception as e:
            logger.warning("JSON 解密失败: %s", e)
            return decryption_failed_response()


class FormDataDecryptStrategy(DecryptStrategy):
    """multipart/form-data：meta_json_encrypted 为加密信封。"""

    def supports(self, ctx: EncryptionContext) -> bool:
        return "multipart/form-data" in ctx.content_type

    async def apply(self, ctx: EncryptionContext) -> Response | None:
        request = ctx.request
        path = ctx.path
        try:
            # 加密体检查：缺少 meta_json_encrypted 视为未按加密协议发送
            form = await request.form()
            meta_encrypted_str = form.get("meta_json_encrypted")
            if not meta_encrypted_str:
                logger.warning("FormData 未按加密协议发送 | path=%s", path)
                return encryption_required_response()
            meta_encrypted = json.loads(meta_encrypted_str)
            if not is_encrypted_body(meta_encrypted):
                logger.warning("FormData meta 未按加密协议发送 | path=%s", path)
                return encryption_required_response()

            timestamp = int(form.get("timestamp", 0))
            nonce = form.get("nonce", "")
            signature = form.get("signature", "")

            session = await ctx.session_service.get_session(
                meta_encrypted.get("keyId", ""),
                session_id=request.state.client.session_id,
            )
            if session is None:
                return session_invalid_response()

            meta_str = AesGcmEngine.decrypt_payload(
                EncryptedPayload(
                    encrypted=meta_encrypted["encrypted"],
                    nonce=meta_encrypted["nonce"],
                    key_id=meta_encrypted["keyId"],
                ),
                session.aes_key,
            )
            meta = json.loads(meta_str)

            # 签名密钥从会话 AES 密钥派生（每个会话独立）
            signing_key = derive_signing_key(session.aes_key, ctx.sign_context)
            sig_ok, sig_reason = verify_signature(
                params=meta,
                secret=signing_key.hex(),
                signature=signature,
                timestamp=timestamp,
                nonce=nonce,
                exclude_keys=_EXCLUDED_FROM_SIGNATURE,
                timestamp_tolerance_ms=SIGNATURE_TIMESTAMP_TOLERANCE_MS,
            )
            if not sig_ok:
                logger.warning("FormData 签名验证失败: %s", sig_reason)
                return session_invalid_response()

            # nonce 重放防护（签名通过后检查，确保同一请求不被重复执行）
            if not nonce:
                logger.warning(
                    "FormData 请求空 nonce 拒绝 | key_id=%s", _key_id_preview(session)
                )
                return empty_nonce_response()
            if not await self._nonce_cache.check_and_store(session.key_id, nonce):
                logger.warning(
                    "FormData 请求重放拦截 | key_id=%s | nonce=%s",
                    _key_id_preview(session),
                    nonce[:16] + "...",
                )
                return replay_response()

            request.state.enc_session = session
            ctx.session = session
            logger.debug(
                "FormData 已解密并验证签名 | key_id=%s", _key_id_preview(session)
            )
            return None
        except Exception as e:
            logger.warning("FormData 解密失败: %s", e)
            return meta_decryption_failed_response()
