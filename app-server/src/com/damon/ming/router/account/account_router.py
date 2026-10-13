"""
Account 路由 —— 用户 Token 签发

职责：
  - 为客户端签发身份 token（绑定手机号，模拟阶段用随机 phone）
  - 服务端根据 UA 计算 device_id，与 token 一起下发
  - 创建 session_id（token + device_id 的唯一会话标识）
  - 同一手机号再次请求返回已有 token（幂等）
  - 同一 (token, device_id) 组合复用同一 session_id

TODO: 后期接入真实手机号 + 验证码校验

用法：
  POST /api/account/token/v1  body: { "phone": "+8613800138000" }
    → { "token": "xxx", "device_id": "dev_sha256abc...", "session_id": "uuid..." }
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
    create_session,
    get_active_session,
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
      2. 注册/更新设备（设备身份独立，不归属用户）
      3. 检查该 phone 是否已有 token → 有则复用（幂等）
      4. 无 → 生成 token → 绑定 phone
      5. 查找或创建 session（同一 token+device 复用）
    """
    # 1. 从 ctx 获取 UA → 计算设备指纹
    ctx = request.state.ctx
    ua_profile = get_ua_profile(ctx)
    device_id = compute_device_id(ua_profile) if ua_profile else ""
    ua_hash = compute_ua_hash(ua_profile)

    # 2. 注册设备（设备身份独立，不绑定 phone）
    if device_id and ua_profile:
        register_device(
            device_id=device_id,
            ua_hash=ua_hash,
            raw_ua=ua_profile.raw_ua,
            platform=ua_profile.platform,
            screen=ua_profile.screen,
            lang=ua_profile.lang,
            tz=ua_profile.tz,
        )

    # 3. 检查该 phone 是否已有 token（幂等）
    existing_token = get_token_by_phone(body.phone)
    if existing_token:
        # 查找该组合的活跃会话
        active_session = get_active_session(existing_token, device_id)
        session_id = (
            active_session.session_id
            if active_session
            else create_session(existing_token, device_id, ua_hash)
        )

        logger.info(
            "Token 已存在（复用） | phone=%s device_id=%s session_id=%s",
            _mask_phone(body.phone),
            device_id[:12] + "...",
            session_id[:8] + "...",
        )

        return BaseSuccessResponse(
            code=ErrorCode.OK,
            data=TokenResponseData(
                token=existing_token,
                device_id=device_id,
                session_id=session_id,
            ),
        )

    # 4. 新 phone → 签发 token
    token = secrets.token_hex(32)
    bind_token(body.phone, token)

    # 5. 创建会话
    session_id = create_session(token, device_id, ua_hash)

    logger.info(
        "Token 已签发 | phone=%s device_id=%s session_id=%s",
        _mask_phone(body.phone),
        device_id[:12] + "...",
        session_id[:8] + "...",
    )

    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data=TokenResponseData(
            token=token,
            device_id=device_id,
            session_id=session_id,
        ),
    )


def _mask_phone(phone: str) -> str:
    """手机号脱敏：+8613800138000 → +86***38000"""
    if len(phone) > 4:
        return phone[:3] + "***" + phone[-4:]
    return "***"
