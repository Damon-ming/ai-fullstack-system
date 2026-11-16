# app-server/src/com/damon/ming/middleware/auth_middleware.py
"""
认证中间件 —— 单个设备 token 校验与闲置续期。

职责：
  - 公开路径白名单放行（PUBLIC_PATHS，精确匹配）
  - 从 request.state.client 获取 token
  - 从 X-Client-UA 计算设备指纹，匹配设备会话后填入 user_id 和 session_id

不负责：
  - 解析头部（由 ContextMiddleware 统一处理）
  - token/session 管理（由 router/account/service/account_service.py 负责）
"""

from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.ua_fingerprint import compute_device_id
from src.com.damon.ming.router.account.service.account_service import AccountService
from src.com.damon.ming.schemas.response import BaseBizFailedData, BaseFailedResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = pin("middleware.auth")

# 无需认证的路径（精确匹配 —— 新增端点默认需要认证）
# /ping 与 /health 不在此列：middleware/health.py 在最外层直接短路，不进入中间件栈。
PUBLIC_PATHS = frozenset(
    {
        "/api/account/login/v1",
        "/api/encryption/key/v1",
    }
)


class AuthMiddleware(BaseHTTPMiddleware):
    """设备 token 校验中间件。"""

    async def dispatch(self, request: Request, call_next) -> JSONResponse:
        client = request.state.client

        # 1. 公开路径放行
        if _is_public_path(request.url.path):
            return await call_next(request)

        # 2. token 校验并延长该设备的 7 天闲置期限
        if not client.token:
            logger.warning(
                "认证失败: 缺少 Token | path=%s client=%s",
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.MISSING_TOKEN,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_MISSING_TOKEN)),
                ).model_dump(),
            )

        profile = request.state.ctx.ua_profile
        if (
            profile is None
            or not profile.raw_ua
            or not profile.platform
            or not profile.screen
        ):
            logger.warning("认证失败: 设备指纹不匹配 | path=%s", request.url.path)
            return JSONResponse(
                status_code=401,
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.INVALID_SESSION,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_INVALID_SESSION)),
                ).model_dump(),
            )

        device_id = compute_device_id(profile)
        identity = AccountService.authenticate_token(client.token, device_id)
        if identity is None:
            return JSONResponse(
                status_code=401,
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.INVALID_TOKEN,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_INVALID_TOKEN)),
                ).model_dump(),
            )
        # identity == (user_id, session_id)
        client.user_id, client.session_id = identity
        client.device_id = device_id
        return await call_next(request)


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS
