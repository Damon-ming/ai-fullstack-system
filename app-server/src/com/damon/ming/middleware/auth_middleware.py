# app-server/src/com/damon/ming/middleware/auth_middleware.py
"""
认证中间件 —— Token + 设备 + UA 校验。

职责：
  - 从 request.state.ctx 获取已解析的 token / device_id / UA
  - 校验 token → 得到对应 phone
  - 校验 device_id 属于该 phone
  - 校验 UA 是否与签发时一致（可选的安全加固）

不负责：
  - 解析头部（由 ContextMiddleware 统一处理）
  - token 白名单管理（由 router/account/token_store.py 负责）
"""

from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.request_context import get_ua_profile
from src.com.damon.ming.middleware.ua_fingerprint import has_ua_changed_significantly
from src.com.damon.ming.router.account.token_store import (
    get_device,
    get_phone_by_token,
    is_token_valid,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = pin("middleware.auth")

# 无需认证的路径前缀
PUBLIC_PATH_PREFIXES = (
    "/api/encryption",
    "/api/account",
    "/health",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Token + 设备 + UA 校验中间件。"""

    async def dispatch(self, request: Request, call_next) -> JSONResponse:
        ctx = request.state.ctx

        # 1. 公开路径放行
        if _is_public_path(request.url.path):
            return await call_next(request)

        # 2. token 校验
        if ctx.token is None:
            logger.warning(
                "认证失败: 缺少 Token | path=%s client=%s",
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "code": ErrorCode.AUTH.MISSING_TOKEN,
                    "data": {"error_msg": "Missing authentication token"},
                },
            )

        if not is_token_valid(ctx.token):
            logger.warning(
                "认证失败: 无效 Token | path=%s token_prefix=%s",
                request.url.path,
                ctx.token[:8] + "...",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "code": ErrorCode.AUTH.INVALID_TOKEN,
                    "data": {"error_msg": "Invalid or expired token"},
                },
            )

        phone = get_phone_by_token(ctx.token)

        # 3. 校验 device_id 属于该用户
        if ctx.device_id:
            device = get_device(ctx.device_id)
            if device is None:
                logger.warning(
                    "认证失败: 未注册设备 | path=%s phone_prefix=%s device_id=%s",
                    request.url.path,
                    phone[:3] + "***" if phone else "unknown",
                    ctx.device_id[:12] + "...",
                )
                return JSONResponse(
                    status_code=401,
                    content={
                        "code": ErrorCode.AUTH.UNREGISTERED_DEVICE,
                        "data": {"error_msg": "Device not registered"},
                    },
                )
            if device.phone != phone:
                logger.warning(
                    "认证失败: 设备归属不一致 | path=%s token_phone=%s device_phone=%s",
                    request.url.path,
                    phone[:3] + "***" if phone else "unknown",
                    device.phone[:3] + "***" if device.phone else "unknown",
                )
                return JSONResponse(
                    status_code=401,
                    content={
                        "code": ErrorCode.AUTH.DEVICE_MISMATCH,
                        "data": {"error_msg": "Device does not belong to this user"},
                    },
                )

        # 4. UA 一致性校验
        if ctx.client_ua and ctx.device_id:
            device = get_device(ctx.device_id)
            if device:
                ua_profile = get_ua_profile(ctx)
                if ua_profile and has_ua_changed_significantly(device.ua_hash, ua_profile):
                    logger.info(
                        "UA 发生变化 | phone=%s device_id=%s",
                        phone[:3] + "***" if phone else "unknown",
                        ctx.device_id[:12] + "...",
                    )
                    # 当前策略：仅记录，不阻断（宽松模式）

        # 5. 注入 request.state，供下游路由使用
        request.state.device_token = ctx.token
        request.state.phone = phone
        request.state.device_id = ctx.device_id
        return await call_next(request)


def _is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)
