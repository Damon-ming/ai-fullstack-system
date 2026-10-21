# app-server/src/com/damon/ming/router/encryption/encryption_router.py
"""
密钥交换路由

端点：
  GET  /api/encryption/key/v1        → 获取 RSA 公钥（PEM 格式）
  POST /api/encryption/session/v1    → 注册 AES 会话（客户端传来 RSA 加密的 AES 密钥）

安全加固：
  - session 注册要求携带有效 token（Cookie / Authorization）
  - 注册时校验 session_id 有效且属于该 token
  - 注册时把 session_id 绑定到加密会话
  - 注册前撤销该 session_id 的旧加密会话（防止僵尸密钥）
"""

import base64

from fastapi import APIRouter, Body, Request
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.account.token_store import get_session, is_token_valid
from src.com.damon.ming.schemas.response import (
    BaseBizFailedData,
    BaseFailedResponse,
    BaseSuccessResponse,
)

logger = pin("encryption.router")

router = APIRouter(prefix="/api/encryption", tags=["加密体系"])


@router.get("/key/v1")
@limiter.limit("30/minute")
async def get_public_key(request: Request):
    """
    获取服务端 RSA 公钥。

    客户端拿到公钥后，用它加密自己生成的 AES-256 密钥，
    再通过 POST /session/v1 注册会话。
    """
    sm = request.state.session_service
    pem = sm.rsa_key_pair.get_public_key_pem()
    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data={
            "publicKey": pem.decode("utf-8"),
            "algorithm": "RSA-OAEP-256",
        },
    )


@router.post("/session/v1")
@limiter.limit("10/minute")
async def register_session(
    request: Request,
    encrypted_aes_key: str = Body(
        ..., alias="encryptedAesKey", description="RSA-OAEP 加密的 AES 密钥 (base64)"
    ),
):
    """
    注册 AES 会话。

    客户端生成 AES-256 密钥 → 用 RSA 公钥加密 → 发送到这里。
    服务端用 RSA 私钥解密，存储会话，返回 keyId。

    安全要求：
      - 请求需携带有效 token
      - X-Session-ID header 必须存在且有效（session 属于该 token）
      - 会话将绑定到该 session_id，注册前撤销该 session 的旧密钥
    """
    ctx = request.state.ctx
    sm = request.state.session_service

    # 1. 校验 token
    if not ctx.token or not is_token_valid(ctx.token):
        return BaseFailedResponse(
            code=ErrorCode.AUTH.INVALID_TOKEN,
            data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_INVALID_TOKEN)),
        )

    # 2. 校验 session_id
    if not ctx.session_id:
        return BaseFailedResponse(
            code=ErrorCode.AUTH.MISSING_SESSION,
            data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_MISSING_SESSION)),
        )

    session = get_session(ctx.session_id)
    if session is None:
        return BaseFailedResponse(
            code=ErrorCode.AUTH.INVALID_SESSION,
            data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_INVALID_SESSION)),
        )

    # 3. 防伪造：session 必须属于该 token
    if session.token != ctx.token:
        logger.warning(
            "Session 归属不匹配 | session_token=%s request_token=%s",
            session.token[:8] + "...",
            ctx.token[:8] + "...",
        )
        return BaseFailedResponse(
            code=ErrorCode.AUTH.SESSION_TOKEN_MISMATCH,
            data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_SESSION_MISMATCH)),
        )

    # 4. 注册加密会话（原子替换：清旧录 + 插新录在同一事务）
    try:
        encrypted_aes_key_bytes = base64.b64decode(encrypted_aes_key)
        enc_session = sm.register_and_replace(encrypted_aes_key_bytes, ctx.session_id)
    except ValueError as e:
        logger.warning("会话注册失败（密钥格式错误）: %s", e)
        return BaseFailedResponse(
            code=ErrorCode.ENCRYPT.INVALID_KEY_FORMAT,
            data=BaseBizFailedData(error_msg=t(I18nKey.ENCRYPT_INVALID_KEY_FORMAT)),
        )
    except Exception:
        logger.exception("会话注册失败")
        return BaseFailedResponse(
            code=ErrorCode.ENCRYPT.SESSION_REG_FAILED,
            data=BaseBizFailedData(error_msg=t(I18nKey.ENCRYPT_SESSION_REG_FAILED)),
        )

    logger.info(
        "加密会话注册 | key_id=%s session_id=%s",
        enc_session.key_id[:12] + "...",
        ctx.session_id[:8] + "...",
    )
    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data={
            "keyId": enc_session.key_id,
            "expiresIn": enc_session.ttl_seconds,
        },
    )
