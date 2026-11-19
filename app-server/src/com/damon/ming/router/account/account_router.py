# app-server/src/com/damon/ming/router/account/account_router.py
"""
Account 路由 —— 用户登录 / Token 签发 / 资料管理

职责：
  - 为每台设备签发一个会话 token
  - 服务端根据 UA 计算并保存设备指纹
  - 内部 session_id 用于关联加密会话，不下发客户端
  - 内部用户 ID 稳定，客户端凭据按设备独立
  - 用户资料读取与修改（昵称）

用法：
  POST /api/account/login/v1     body: { "phone": "+8613800138000", "password": "Abc123_45" }
    → { "token": "...", "is_new": false }
  GET  /api/account/profile/get/v1
    → { "name": "Murphy" }
  POST /api/account/profile/update/v1   body: { "name": "NewName" }
    → { "name": "NewName" }

profile 拆成两个路径的原因：加密白名单按路径前缀匹配，
GET 无 body 可加密需放行，POST 有 body 必须加密，同一前缀无法区分。
"""

from fastapi import APIRouter, Request
from src.com.damon.ming.app.thread_pools import (
    get_database_pool,
    run_in_pool,
)
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
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
    create_session,
    get_user_profile,
    login_or_register,
    register_device,
    revoke_session,
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
      4. 创建 session → 返回 token + is_new
    """
    # 登录必须具有可复算的设备指纹，否则后续请求无法完成设备校验。
    ua_profile = request.state.ctx.ua_profile
    if (
        ua_profile is None
        or not ua_profile.raw_ua
        or not ua_profile.platform
        or not ua_profile.screen
    ):
        return BaseFailedResponse(
            code=ErrorCode.VALIDATION.PARAM_FORMAT,
            data=BaseBizFailedData(error_msg="缺少有效的 X-Client-UA 设备信息"),
        )

    # 1. 登录或自动注册
    try:
        user_id, is_new = await run_in_pool(
            get_database_pool(),
            login_or_register,
            body.phone,
            body.password,
        )
    except ValueError as e:
        if str(e) == "PHONE_PASSWORD_MISMATCH":
            return BaseFailedResponse(
                code=ErrorCode.ACCOUNT.PHONE_PASSWORD_MISMATCH,
                data=BaseBizFailedData(error_msg="手机号或密码错误"),
            )
        raise

    # 2. 从 ctx 获取 UA → 计算设备指纹
    device_id = compute_device_id(ua_profile)
    ua_hash = compute_ua_hash(ua_profile)

    # 3. 注册设备（设备身份独立，不绑定 phone）
    register_device(
        device_id=device_id,
        ua_hash=ua_hash,
        raw_ua=ua_profile.raw_ua,
    )

    # 4. 创建会话（原子操作：过期该设备旧会话 + 插入新会话）
    token = create_session(user_id, device_id)

    action = "注册+登录" if is_new else "登录"
    logger.info(
        "%s完成 | phone=%s device_id=%s",
        action,
        _mask_phone(body.phone),
        device_id[:12] + "..." if device_id else "",
    )

    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data=TokenResponseData(
            token=token,
            is_new=is_new,
        ),
    )


@router.post("/logout/v1", response_model=BaseSuccessResponse[dict])
@limiter.limit("20/minute")
async def logout(request: Request):
    """退出当前设备，立即撤销其会话 token。"""
    await run_in_pool(
        get_database_pool(), revoke_session, request.state.client.session_id
    )
    return BaseSuccessResponse(code=ErrorCode.OK, data={})


@router.get("/profile/get/v1", response_model=BaseSuccessResponse[ProfileResponseData])
@limiter.limit("20/minute")
async def get_profile(request: Request):
    """
    获取当前用户资料（需认证，token 由 AuthMiddleware 校验）。

    从请求上下文提取 token → 查询用户昵称。
    路径独立于 update：GET 无 body，命中加密白名单明文放行。
    """
    client = request.state.client
    user = get_user_profile(client.user_id)
    name = user.name if user else ""

    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data=ProfileResponseData(name=name),
    )


@router.post(
    "/profile/update/v1", response_model=BaseSuccessResponse[ProfileResponseData]
)
@limiter.limit("20/minute")
async def update_profile(body: ProfileResponseData, request: Request):
    """
    更新当前用户昵称（需认证，token 由 AuthMiddleware 校验）。

    从请求上下文提取 token → 更新 users 表 name 字段。
    路径独立于 get：POST 携带 body，必须走加密通道。
    """
    client = request.state.client
    name = body.name.strip()[:64]
    update_user_name(client.user_id, name)

    logger.info("用户资料已更新 | user_id=%s name=%s", client.user_id, name)

    return BaseSuccessResponse(
        code=ErrorCode.OK,
        data=ProfileResponseData(name=name),
    )


def _mask_phone(phone: str) -> str:
    """手机号脱敏：+8613800138000 → +86***38000"""
    if len(phone) > 4:
        return phone[:3] + "***" + phone[-4:]
    return "***"
