# app-server/src/com/damon/ming/router/account/account_router.py
"""
Account 路由 —— 用户登录 / Token 签发 / 资料管理

职责：
  - 为客户端签发身份 token（绑定手机号，模拟阶段用随机 phone）
  - 服务端根据 UA 计算 device_id，与 token 一起下发
  - 创建 session_id（token + device_id 的唯一会话标识）
  - 同一手机号再次请求返回已有 token（幂等）
  - 同一 (token, device_id) 组合复用同一 session_id
  - 用户资料读取与修改（昵称）

用法：
  POST /api/account/login/v1     body: { "phone": "+8613800138000" }
    → { "token": "xxx", "device_id": "dev_sha256abc...", "session_id": "uuid..." }
  GET  /api/account/profile/v1
    → { "name": "Murphy" }
  POST /api/account/profile/v1   body: { "name": "NewName" }
    → { "name": "NewName" }
"""

import secrets

from fastapi import APIRouter, Request
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.middleware.request_context import get_ua_profile
from src.com.damon.ming.middleware.ua_fingerprint import (
    compute_device_id,
    compute_ua_hash,
)
from src.com.damon.ming.router.account.schemas.bean import (
    ProfileResponseData,
    TokenRequest,
    TokenResponseData,
)
from src.com.damon.ming.router.account.token_store import (
    bind_token,
    create_session,
    get_active_session,
    get_token_by_phone,
    get_user_profile,
    is_token_valid,
    register_device,
    update_user_name,
)
from src.com.damon.ming.schemas.response import BaseSuccessResponse

logger = pin("account.router")

router = APIRouter(prefix="/api/account", tags=["账号体系"])


@router.post("/login/v1", response_model=BaseSuccessResponse[TokenResponseData])
@limiter.limit("5/minute")
async def login(body: TokenRequest, request: Request):
    """
    登录 —— 签发用户 Token。

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


@router.get("/profile/v1", response_model=BaseSuccessResponse[ProfileResponseData])
@limiter.limit("20/minute")
async def get_profile(request: Request):
    """
    获取当前用户资料。

    从请求上下文提取 token → 查询用户昵称。
    公开路径，但需要有效的 token（通过 Cookie / Authorization Bearer 传递）。
    """
    ctx = request.state.ctx
    if not ctx.token or not is_token_valid(ctx.token):
        return BaseSuccessResponse(
            code=ErrorCode.AUTH_INVALID_TOKEN,
            data=ProfileResponseData(name=""),
        )

    user = get_user_profile(ctx.token)
    name = user.name if user else ""

    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data=ProfileResponseData(name=name),
    )


@router.post("/profile/v1", response_model=BaseSuccessResponse[ProfileResponseData])
@limiter.limit("20/minute")
async def update_profile(body: ProfileResponseData, request: Request):
    """
    更新当前用户昵称。

    从请求上下文提取 token → 更新 users 表 name 字段。
    """
    ctx = request.state.ctx
    if not ctx.token or not is_token_valid(ctx.token):
        return BaseSuccessResponse(
            code=ErrorCode.AUTH_INVALID_TOKEN,
            data=ProfileResponseData(name=""),
        )

    name = body.name.strip()[:64]
    update_user_name(ctx.token, name)

    logger.info("用户资料已更新 | token_prefix=%s name=%s", ctx.token[:8] + "...", name)

    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data=ProfileResponseData(name=name),
    )


def _mask_phone(phone: str) -> str:
    """手机号脱敏：+8613800138000 → +86***38000"""
    if len(phone) > 4:
        return phone[:3] + "***" + phone[-4:]
    return "***"
