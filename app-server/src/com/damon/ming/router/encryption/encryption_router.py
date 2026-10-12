# app-server/src/com/damon/ming/router/encryption/encryption_router.py
"""
密钥交换路由

端点：
  GET  /api/encryption/key/v1        → 获取 RSA 公钥（PEM 格式）
  POST /api/encryption/session/v1    → 注册 AES 会话（客户端传来 RSA 加密的 AES 密钥）

安全加固：
  - session 注册要求携带有效 token（Cookie / Authorization）
  - 注册时把 token 对应的 device_id 绑定到加密会话
  - 请求时解密中间件可校验 session 归属（需配合 binding_id 查询）
"""

import base64

from fastapi import APIRouter, Body, Request
from src.com.damon.ming.encryption.globals import get_key_manager
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.account.token_store import get_device, is_token_valid
from src.com.damon.ming.schemas.response import (
    BaseFailedResponse,
    BaseSuccessResponse,
)

logger = pin("encryption.router")


router = APIRouter(prefix="/api/encryption", tags=["加密体系"])


@router.get("/key/v1")
async def get_public_key():
    """
    获取服务端 RSA 公钥。

    客户端拿到公钥后，用它加密自己生成的 AES-256 密钥，
    再通过 POST /session/v1 注册会话。
    """
    km = get_key_manager()
    pem = km.get_public_key_pem()
    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data={
            "publicKey": pem.decode("utf-8"),
            "algorithm": "RSA-OAEP-256",
        },
    )


@router.post("/session/v1")
async def register_session(
    request: Request,
    encryptedAesKey: str = Body(..., description="RSA-OAEP 加密的 AES 密钥 (base64)"),
):
    """
    注册 AES 会话。

    客户端生成 AES-256 密钥 → 用 RSA 公钥加密 → 发送到这里。
    服务端用 RSA 私钥解密，存储会话，返回 keyId。

    安全要求：
      - 请求需携带有效 token（通过 auth_middleware 或此处校验）
      - X-Device-ID header 必须存在且已注册
      - 会话将绑定到该 device_id，解密时校验归属
    """
    km = get_key_manager()
    ctx = request.state.ctx

    # 1. 校验 token + device_id（加密端点本身在 PUBLIC_PATH 中跳过 auth_middleware，
    #    所以这里手动从 ctx 获取并校验）
    if not ctx.token or not is_token_valid(ctx.token):
        return BaseFailedResponse(
            code=ErrorCode.AUTH.INVALID_TOKEN,
            data={"error_msg": "Valid token required for session registration"},
        )

    if not ctx.device_id:
        return BaseFailedResponse(
            code=ErrorCode.AUTH.MISSING_TOKEN,
            data={"error_msg": "Missing X-Device-ID header"},
        )

    device = get_device(ctx.device_id)
    if device is None:
        return BaseFailedResponse(
            code=ErrorCode.AUTH.UNREGISTERED_DEVICE,
            data={"error_msg": "Device not registered, please obtain token first"},
        )

    # 2. 注册加密会话（纯密钥操作，不感知业务绑定）
    try:
        encrypted_aes_key = base64.b64decode(encryptedAesKey)
        session = km.register_session(encrypted_aes_key)
    except ValueError as e:
        logger.warning("会话注册失败（密钥格式错误）: %s", e)
        return BaseFailedResponse(
            code=ErrorCode.ENCRYPT.INVALID_KEY_FORMAT,
            data={"error_msg": "Invalid AES key format"},
        )
    except Exception:
        logger.exception("会话注册失败")
        return BaseFailedResponse(
            code=ErrorCode.ENCRYPT.SESSION_REG_FAILED,
            data={"error_msg": "Session registration failed"},
        )

    # 3. 业务层关联：将加密会话绑定到设备（加密模块不感知此逻辑）
    key_store = getattr(km, "_key_store", None)
    if key_store is not None and hasattr(key_store, "bind_session"):
        key_store.bind_session(session.key_id, ctx.device_id)

    logger.info(
        "加密会话注册 | key_id=%s device_id=%s",
        session.key_id[:12] + "...",
        ctx.device_id[:12] + "...",
    )
    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data={
            "keyId": session.key_id,
            "expiresIn": session.ttl_seconds,
        },
    )


