# app-server/src/com/damon/ming/middleware/auth_middleware.py
"""
认证中间件 —— Token + Session + UA 校验。

职责：
  - 从 request.state.ctx 获取已解析的 token / session_id / UA
  - 校验 token → 得到对应 phone
  - 校验 session_id 有效且属于该 token（替代旧的 device 归属校验）
  - 校验 UA 是否与签发时一致（可选的安全加固）

不负责：
  - 解析头部（由 ContextMiddleware 统一处理）
  - token/session 管理（由 router/account/token_store.py 负责）
"""

from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.request_context import get_ua_profile
from src.com.damon.ming.middleware.ua_fingerprint import has_ua_changed_significantly
from src.com.damon.ming.router.account.token_store import (
    get_phone_by_token,
    get_session,
    is_token_valid,
)
from src.com.damon.ming.schemas.response import BaseBizFailedData, BaseFailedResponse
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
    """Token + Session + UA 校验中间件。"""

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
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.MISSING_TOKEN,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_MISSING_TOKEN)),
                ).model_dump(),
            )

        if not is_token_valid(ctx.token):
            logger.warning(
                "认证失败: 无效 Token | path=%s token_prefix=%s",
                request.url.path,
                ctx.token[:8] + "...",
            )
            return JSONResponse(
                status_code=401,
                content=BaseFailedResponse(
                    code=ErrorCode.AUTH.INVALID_TOKEN,
                    data=BaseBizFailedData(error_msg=t(I18nKey.AUTH_INVALID_TOKEN)),
                ).model_dump(),
            )

        phone = get_phone_by_token(ctx.token)

        # 3. 校验 session_id
        if ctx.session_id:
            session = get_session(ctx.session_id)
            if session is None:
                logger.warning(
                    "认证失败: 无效会话 | path=%s phone_prefix=%s session_id=%s",
                    request.url.path,
                    phone[:3] + "***" if phone else "unknown",
                    ctx.session_id[:8] + "...",
                )
                return JSONResponse(
                    status_code=401,
                    content=BaseFailedResponse(
                        code=ErrorCode.AUTH.INVALID_SESSION,
                        data=BaseBizFailedData(
                            error_msg=t(I18nKey.AUTH_INVALID_SESSION)
                        ),
                    ).model_dump(),
                )
            if session.token != ctx.token:
                logger.warning(
                    "认证失败: 会话归属不匹配 | path=%s token_phone=%s session_token_phone=%s",
                    request.url.path,
                    phone[:3] + "***" if phone else "unknown",
                    get_phone_by_token(session.token)[:3] + "***"
                    if session.token
                    else "unknown",
                )
                return JSONResponse(
                    status_code=401,
                    content=BaseFailedResponse(
                        code=ErrorCode.AUTH.SESSION_TOKEN_MISMATCH,
                        data=BaseBizFailedData(
                            error_msg=t(I18nKey.AUTH_SESSION_MISMATCH)
                        ),
                    ).model_dump(),
                )

        # 4. UA 一致性校验（基于 session 签发时的 UA）
        if ctx.client_ua and ctx.session_id:
            session = get_session(ctx.session_id)
            if session:
                ua_profile = get_ua_profile(ctx)
                if ua_profile and has_ua_changed_significantly(
                    session.ua_hash, ua_profile
                ):
                    logger.info(
                        "UA 发生变化 | phone=%s session_id=%s",
                        phone[:3] + "***" if phone else "unknown",
                        ctx.session_id[:8] + "...",
                    )
                    # 当前策略：仅记录，不阻断（宽松模式）

        # 5. 注入 request.state，供下游路由使用
        request.state.device_token = ctx.token
        request.state.phone = phone
        request.state.device_id = ctx.device_id
        request.state.session_id = ctx.session_id
        return await call_next(request)


def _is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)
