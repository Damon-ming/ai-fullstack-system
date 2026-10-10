# app-server/src/com/damon/ming/middleware/auth_middleware.py
"""
认证中间件 —— 请求 Token 校验。

职责：
  - 从请求中提取 device_auth_token（Cookie / Authorization）
  - 校验 token 是否在白名单中
  - 公开路径直接放行

不负责：
  - token 白名单管理（由 router/account/token_store.py 负责）
  - debug 环境判断（由 main.py 控制是否注册此中间件）
"""

from src.com.damon.ming.log import pin
from src.com.damon.ming.router.account.token_store import is_token_valid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = pin("middleware.auth")

# Cookie 中 token 的 key 名（与前端约定一致）
TOKEN_COOKIE_NAME = "device_auth_token"

# 无需认证的路径前缀
PUBLIC_PATH_PREFIXES = (
    "/api/encryption",
    "/api/account",
    "/health",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Token 白名单校验中间件。"""

    async def dispatch(self, request: Request, call_next) -> JSONResponse:
        # 1. 公开路径放行
        if _is_public_path(request.url.path):
            return await call_next(request)

        # 2. 提取 token
        token = _extract_token(request)
        if token is None:
            logger.warning(
                "认证失败: 缺少 Token | path=%s client=%s",
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "code": 40301,
                    "data": {"error_msg": "Missing authentication token"},
                },
            )

        # 3. 白名单校验
        if not is_token_valid(token):
            logger.warning(
                "认证失败: 无效 Token | path=%s token_prefix=%s",
                request.url.path,
                token[:8] + "...",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "code": 40302,
                    "data": {"error_msg": "Invalid or expired token"},
                },
            )

        # 4. 注入 request.state，供下游路由使用
        request.state.device_token = token
        return await call_next(request)


def _is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


def _extract_token(request: Request) -> str | None:
    """从请求中提取 device_auth_token（Cookie / Authorization Bearer）。"""
    cookie_header = request.headers.get("cookie", "")
    if cookie_header:
        for pair in cookie_header.split(";"):
            pair = pair.strip()
            if pair.startswith(f"{TOKEN_COOKIE_NAME}="):
                return pair[len(TOKEN_COOKIE_NAME) + 1 :].strip()

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None
