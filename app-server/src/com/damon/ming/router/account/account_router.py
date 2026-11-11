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
  POST /api/account/login/v1     body: { "phone": "+8613800138000", "password": "Abc123_45" }
    → { "token": "xxx", "device_id": "dev_sha256abc...", "session_id": "uuid...", "is_new": false }
  GET  /api/account/profile/v1
    → { "name": "Murphy" }
  POST /api/account/profile/v1   body: { "name": "NewName" }
    → { "name": "NewName" }
"""

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
    LoginRequest,
    ProfileResponseData,
    TokenResponseData,
)
from src.com.damon.ming.router.account.token_store import (
    create_or_refresh_session,
    get_user_profile,
    login_or_register,
    refresh_token_ttl,
    register_device,
    update_user_name,
)
from src.com.damon.ming.schemas.response import (
    BaseBizFailedData,
    BaseFailedResponse,
    BaseSuccessResponse,
)

logger = pin("account.router")

router = APIRouter(prefix="/api/account", tags=["账号体系"])


@router.post("/login/v1", response_model=BaseSuccessResponse[TokenResponseData])
@limiter.limit("5/minute")
async def login(body: LoginRequest, request: Request):
    """
    登录 / 自动注册 —— 手机号 + 密码一键完成。

    流程：
      1. phone 已注册 → 验 password → 对则登录，错则返回 200004002
      2. phone 未注册 → 自动注册 + 登录
      3. 解析 X-Client-UA → 计算 device_id → 注册设备
      4. 创建 session → 返回 token + device_id + session_id + is_new
    """
    # 1. 登录或自动注册
    try:
        user_token, is_new = login_or_register(body.phone, body.password)
    except ValueError as e:
        if str(e) == "PHONE_PASSWORD_MISMATCH":
            return BaseFailedResponse(
                code=ErrorCode.ACCOUNT.PHONE_PASSWORD_MISMATCH,
                data=BaseBizFailedData(error_msg="手机号或密码错误"),
            )
        raise

    # 2. 从 ctx 获取 UA → 计算设备指纹
    ctx = request.state.ctx
    ua_profile = get_ua_profile(ctx)
    device_id = compute_device_id(ua_profile) if ua_profile else ""
    ua_hash = compute_ua_hash(ua_profile)

    # 3. 注册设备（设备身份独立，不绑定 phone）
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

    # 4. 创建/刷新会话（原子操作：过期旧会话 + 插入新会话）
    session_id = create_or_refresh_session(user_token, device_id, ua_hash)

    # 5. SECURITY: 登录成功，刷新 token 滚动 TTL（P1-7 修复）
    refresh_token_ttl(user_token)

    action = "注册+登录" if is_new else "登录"
    logger.info(
        "%s完成 | phone=%s device_id=%s session_id=%s",
        action,
        _mask_phone(body.phone),
        device_id[:12] + "..." if device_id else "",
        session_id[:8] + "...",
    )

    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data=TokenResponseData(
            token=user_token,
            device_id=device_id,
            session_id=session_id,
            is_new=is_new,
        ),
    )


@router.get("/profile/v1", response_model=BaseSuccessResponse[ProfileResponseData])
@limiter.limit("20/minute")
async def get_profile(request: Request):
    """
    获取当前用户资料（需认证，token 由 AuthMiddleware 校验）。

    从请求上下文提取 token → 查询用户昵称。
    """
    ctx = request.state.ctx
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
    更新当前用户昵称（需认证，token 由 AuthMiddleware 校验）。

    从请求上下文提取 token → 更新 users 表 name 字段。
    """
    ctx = request.state.ctx
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
