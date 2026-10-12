"""
Account 路由 —— 用户 Token 签发

职责：
  - 为客户端签发身份 token（绑定手机号，模拟阶段用随机 phone）
  - 服务端根据 UA 计算 device_id，与 token 一起下发
  - 同一手机号再次请求返回已有 token（幂等）

TODO: 后期接入真实手机号 + 验证码校验

用法：
  POST /api/account/token/v1  body: { "phone": "+8613800138000" }
    → { "token": "xxx", "device_id": "dev_sha256abc..." }
"""

import secrets

from fastapi import APIRouter, Request
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.request_context import get_ua_profile
from src.com.damon.ming.middleware.ua_fingerprint import (
    compute_device_id,
    compute_ua_hash,
)
from src.com.damon.ming.router.account.schemas.bean import (
    TokenRequest,
    TokenResponseData,
)
from src.com.damon.ming.router.account.token_store import (
    bind_token,
    get_token_by_phone,
    register_device,
)
from src.com.damon.ming.schemas.response import BaseSuccessResponse

logger = pin("account.router")

router = APIRouter(prefix="/api/account", tags=["账号体系"])


@router.post("/token/v1", response_model=BaseSuccessResponse[TokenResponseData])
async def generate_token(body: TokenRequest, request: Request):
    """
    签发用户 Token。

    流程：
      1. 解析 X-Client-UA header → 计算 device_id
      2. 检查该 phone 是否已有 token → 有则复用（幂等）
      3. 无 → 生成 token → 绑定 phone → 注册设备 → 返回
    """
    # 1. 从 ctx 获取 UA → 计算设备指纹
    ctx = request.state.ctx
    ua_profile = get_ua_profile(ctx)
    device_id = compute_device_id(ua_profile) if ua_profile else ""
    ua_hash = compute_ua_hash(ua_profile)

    # 2. 检查该 phone 是否已有 token（幂等）
    existing_token = get_token_by_phone(body.phone)
    if existing_token:
        logger.info(
            "Token 已存在（复用） | phone=%s device_id=%s",
            _mask_phone(body.phone),
            device_id[:12] + "...",
        )
        # 注册设备（同一 phone 可能在新设备上登录）
        try:
            register_device(device_id, body.phone, ua_hash, existing_token)
        except ValueError as e:
            logger.warning("设备注册冲突: %s", e)
            # 不阻断 token 下发，仅记录

        return BaseSuccessResponse(
            code=ErrorCode.OK,
            data=TokenResponseData(token=existing_token, device_id=device_id),
        )

    # 3. 新 phone → 签发 token
    token = secrets.token_hex(32)
    bind_token(body.phone, token)
    register_device(device_id, body.phone, ua_hash, token)

    logger.info(
        "Token 已签发 | phone=%s device_id=%s",
        _mask_phone(body.phone),
        device_id[:12] + "...",
    )

    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data=TokenResponseData(token=token, device_id=device_id),
    )


def _mask_phone(phone: str) -> str:
    """手机号脱敏：+8613800138000 → +86***38000"""
    if len(phone) > 4:
        return phone[:3] + "***" + phone[-4:]
    return "***"
