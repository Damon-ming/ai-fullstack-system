# app-server/src/com/damon/ming/middleware/auth_middleware.py
"""
认证中间件 —— Token + Session 校验。

职责：
  - 公开路径白名单放行（PUBLIC_PATHS，精确匹配）
  - 从 request.state.client 获取已解析的 token / session_id / UA
  - 校验 token → 得到对应 phone
  - 校验 session_id 有效且属于该 token（替代旧的 device 归属校验）

不负责：
  - 解析头部（由 ContextMiddleware 统一处理）
  - token/session 管理（由 router/account/service/account_service.py 负责）
"""

from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
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
    """Token + Session 校验中间件。"""

    async def dispatch(self, request: Request, call_next) -> JSONResponse:
        client = request.state.client

        # 1. 公开路径放行
        if _is_public_path(request.url.path):
            return await call_next(request)

        # 2. token 校验
        if client.token is None:
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

        if not AccountService.is_token_valid(client.token):
            logger.warning(
                "认证失败: 无效 Token | path=%s token_prefix=%s",
                request.url.path,
                client.token[:8] + "...",
            )
            return JSONResponse(
                status_code=401,
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.INVALID_TOKEN,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_INVALID_TOKEN)),
                ).model_dump(),
            )

        phone = AccountService.get_phone_by_token(client.token)

        # 3. 校验 session_id（SECURITY: 受保护路由强制要求非空 session_id，
        #    防止空 session_id 绕过加密归属校验 —— P1-1 修复）
        if not client.session_id:
            logger.warning(
                "认证失败: 缺少 session_id | path=%s phone_prefix=%s",
                request.url.path,
                phone[:3] + "***" if phone else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.MISSING_SESSION,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_INVALID_SESSION)),
                ).model_dump(),
            )
        session = AccountService.get_session_info(client.session_id)
        if session is None:
            logger.warning(
                "认证失败: 无效会话 | path=%s phone_prefix=%s session_id=%s",
                request.url.path,
                phone[:3] + "***" if phone else "unknown",
                client.session_id[:8] + "...",
            )
            return JSONResponse(
                status_code=401,
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.INVALID_SESSION,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_INVALID_SESSION)),
                ).model_dump(),
            )
        if session.token != client.token:
            logger.warning(
                "认证失败: 会话归属不匹配 | path=%s token_phone=%s session_token_phone=%s",
                request.url.path,
                phone[:3] + "***" if phone else "unknown",
                AccountService.get_phone_by_token(session.token)[:3] + "***"
                if session.token
                else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.SESSION_TOKEN_MISMATCH,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_SESSION_MISMATCH)),
                ).model_dump(),
            )

        return await call_next(request)


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS
