# app-server/src/com/damon/ming/encryption/router.py
"""
密钥交换路由

端点：
  GET  /api/encryption/key        → 获取 RSA 公钥（PEM 格式）
  POST /api/encryption/session    → 注册 AES 会话（客户端传来 RSA 加密的 AES 密钥）

这两个端点本身不加密（它们是加密体系的"引导"阶段）。
"""

import base64

from fastapi import APIRouter, Body, HTTPException
from src.com.damon.ming.encryption.middleware import get_key_manager
from src.com.damon.ming.log import pin
from src.com.damon.ming.schemas.response import BaseSuccessResponse

logger = pin("encryption.router")

router = APIRouter(prefix="/api/encryption", tags=["加密体系"])


@router.get("/key")
async def get_public_key():
    """
    获取服务端 RSA 公钥。

    客户端拿到公钥后，用它加密自己生成的 AES-256 密钥，
    再通过 POST /session 注册会话。
    """
    km = get_key_manager()
    pem = km.get_public_key_pem()
    return BaseSuccessResponse(
        code=10000,
        data={
            "publicKey": pem.decode("utf-8"),
            "algorithm": "RSA-OAEP-256",
        },
    )


@router.post("/session")
async def register_session(
    encryptedAesKey: str = Body(..., description="RSA-OAEP 加密的 AES 密钥 (base64)"),
):
    """
    注册 AES 会话。

    客户端生成 AES-256 密钥 → 用 RSA 公钥加密 → 发送到这里。
    服务端用 RSA 私钥解密，存储会话，返回 keyId。
    """
    km = get_key_manager()
    try:
        encrypted_aes_key = base64.b64decode(encryptedAesKey)
        session = km.register_session(encrypted_aes_key)
        logger.info("新加密会话注册 | key_id=%s", session.key_id)
        return BaseSuccessResponse(
            code=10000,
            data={
                "keyId": session.key_id,
                "expiresIn": session.ttl_seconds,
            },
        )
    except ValueError as e:
        logger.warning("会话注册失败（密钥格式错误）: %s", e)
        raise HTTPException(status_code=400, detail="Invalid AES key")
    except Exception:
        logger.exception("会话注册失败")
        raise HTTPException(status_code=500, detail="Session registration failed")
