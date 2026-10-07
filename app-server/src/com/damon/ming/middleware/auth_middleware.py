# app-server/src/com/damon/ming/middleware/auth_middleware.py
"""
认证中间件 —— Token 白名单验证

临时方案（无账号系统）：
  - 前端在 Cookie 中注入 device_auth_token
  - 服务端维护内存 token 白名单（dict），存在则放行
  - 未来升级：
    * 替换为 JWT / Session 验证
    * token 改为服务端 Set-Cookie + HttpOnly
    * 加入过期时间、刷新机制、设备绑定

安全设计（对齐 HttpOnly 最佳实践）：
  - 当前：前端生成 token 通过 Cookie 头发送（JS 可读，XSS 可窃取）
  - 未来：Set-Cookie: device_auth_token=xxx; HttpOnly; Secure; SameSite=Strict
  - HttpOnly → JS 无法读取 → 防御 XSS
  - Secure → 仅 HTTPS 传输 → 防御中间人
  - SameSite=Strict → 跨站不携带 → 防御 CSRF

不需要认证的路径：
  - /api/encryption/* → 密钥交换阶段，客户端还没有稳定会话
  - /health → 健康检查
  - /docs, /openapi.json → API 文档（开发环境）
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from com.damon.hong.debug import is_debug, is_skip_auth, is_trust_client_env
from src.com.damon.ming.log import pin

logger = pin("middleware.auth")

# 服务端自身环境（来自全局 debug 模块）
SERVER_IS_DEBUG = is_debug()

# Cookie 中 token 的 key 名（与前端约定一致）
TOKEN_COOKIE_NAME = "device_auth_token"

# 无需认证的路径前缀列表
PUBLIC_PATH_PREFIXES = (
    "/api/encryption",
    "/health",
    "/docs",
    "/openapi.json",
    "/favicon.ico",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Token 白名单验证中间件。

    检查流程：
      1. 是否在 PUBLIC_PATH_PREFIXES 中 → 放行
      2. 从 Cookie 头解析 device_auth_token
      3. token 是否在白名单中 → 放行 / 401
    """

    def __init__(self, app: ASGIApp, token_whitelist: set[str] | None = None):
        super().__init(app)
        # token 白名单：优先用注入的，否则用模块级共享实例
        # 模块级实例供 add_token / remove_token 管理函数使用
        self._token_whitelist: set[str] = (
            token_whitelist if token_whitelist is not None else _token_whitelist
        )

    async def dispatch(self, request: Request, call_next) -> JSONResponse:
        # 0. 确定生效环境
        #     服务端 debug 时：信任前端传过来的 X-Client-Env（方便联调测试 release 行为）
        #     服务端 release 时：始终按 release 处理（防止客户端伪造）
        #     is_trust_client_env() 内部已判断 SERVER_IS_DEBUG + 运行时开关
        effective_env = (
            request.headers.get("x-client-env", "debug")
            if is_trust_client_env()
            else "release"
        )

        # 0.5 debug 环境下 skip_auth 开关开启 → 跳过认证
        if is_skip_auth():
            logger.debug("跳过认证（skip_auth 开关开启）| path=%s", request.url.path)
            return await call_next(request)

        # 1. 公开路径直接放行
        if self._is_public_path(request.url.path):
            return await call_next(request)

        # 2. 从 Cookie 解析 token
        token = self._extract_token(request)

        if token is None:
            logger.warning(
                "认证失败: 缺少 Token | path=%s client=%s env=%s",
                request.url.path,
                request.client.host if request.client else "unknown",
                effective_env,
            )
            return JSONResponse(
                status_code=401,
                content={
                    "code": 40301,
                    "data": {"error_msg": "Missing authentication token"},
                },
            )

        # 3. 白名单验证
        if token not in self._token_whitelist:
            logger.warning(
                "认证失败: 无效 Token | path=%s token_prefix=%s env=%s",
                request.url.path,
                token[:8] + "...",
                effective_env,
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
        request.state.effective_env = effective_env
        return await call_next(request)

    # ==== 私有 ============================================================

    def _is_public_path(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        """
        从请求中提取 device_auth_token。

        支持两种方式：
          1. Cookie 头（标准方式，未来 HttpOnly 方案）
          2. Authorization: Bearer <token>（备选，方便 Postman 调试）
        """
        # 方式 1: Cookie 头（前端注入格式：Cookie: device_auth_token=xxx）
        cookie_header = request.headers.get("cookie", "")
        if cookie_header:
            for pair in cookie_header.split(";"):
                pair = pair.strip()
                if pair.startswith(f"{TOKEN_COOKIE_NAME}="):
                    return pair[len(TOKEN_COOKIE_NAME) + 1 :].strip()

        # 方式 2: Authorization Bearer（调试兼容）
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()

        return None


# ---------------------------------------------------------------------------
# 白名单管理（线程安全）
# ---------------------------------------------------------------------------

import threading

_token_lock = threading.Lock()


def add_token(token: str) -> None:
    """注册一个有效 token（客户端首次连接或登录时调用）。"""
    with _token_lock:
        _token_whitelist.add(token)


def remove_token(token: str) -> None:
    """移除 token（登出或安全重置时调用）。"""
    with _token_lock:
        _token_whitelist.discard(token)


def is_token_valid(token: str) -> bool:
    """检查 token 是否在白名单中。"""
    with _token_lock:
        return token in _token_whitelist


# 模块级白名单实例（供 Middleware 和管理函数共享）
_token_whitelist: set[str] = set()
