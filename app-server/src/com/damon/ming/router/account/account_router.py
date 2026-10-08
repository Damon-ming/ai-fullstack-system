"""
Account 路由 —— 设备 Token 签发

职责：
  - 为客户端签发 device_auth_token
  - 服务端生成 token 并存入内存白名单
  - 后续所有请求需携带此 token，AuthMiddleware 校验

TODO: 后期 device_id 替换为手机号，接入账号系统

用法：
  POST /api/account/token/v1  body: { "device_id": "xxx" }  →  { "token": "xxx" }
"""

import secrets

from fastapi import APIRouter
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.auth_middleware import (
    add_token,
    get_token_by_device_id,
)
from src.com.damon.ming.router.account.schemas.bean import (
    TokenRequest,
    TokenResponseData,
)
from src.com.damon.ming.schemas.response import BaseSuccessResponse

logger = pin("account.router")

router = APIRouter(prefix="/api/account", tags=["账号体系"])


@router.post("/token/v1", response_model=BaseSuccessResponse[TokenResponseData])
async def generate_token(body: TokenRequest):
    """
    签发设备 Token。

    同一 device_id 再次请求时直接返回已有 token（幂等），
    避免客户端每次刷新生成新 token 导致旧 token 失效。

    TODO: 后期 device_id 替换为手机号，接入账号系统（JWT / Session）
    """
    # 1. 检查该 device_id 是否已有 token → 直接返回（幂等）
    existing_token = get_token_by_device_id(body.device_id)
    if existing_token:
        logger.info(
            "Token 已存在（复用） | device_id=%s | token_prefix=%s",
            body.device_id,
            existing_token[:8] + "...",
        )
        return BaseSuccessResponse(
            code=10000,
            data=TokenResponseData(token=existing_token),
        )

    # 2. 新 device_id → 生成 token 并绑定
    token = secrets.token_hex(32)
    add_token(token, device_id=body.device_id)

    logger.info(
        "Token 已签发 | device_id=%s | token_prefix=%s",
        body.device_id,
        token[:8] + "...",
    )

    return BaseSuccessResponse(
        code=10000,
        data=TokenResponseData(token=token),
    )
