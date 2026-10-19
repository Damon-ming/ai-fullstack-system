# middleware/i18n_middleware.py
"""
i18n 中间件 —— 解析 X-Language 请求头，设置当前请求的 locale。

注册顺序：在 ContextMiddleware 之后、AuthMiddleware 之前。
"""

from src.com.damon.ming.i18n.locale_negotiator import apply_locale
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class I18nMiddleware(BaseHTTPMiddleware):
    """请求级 locale 设置中间件。"""

    async def dispatch(self, request: Request, call_next):
        apply_locale(request)
        return await call_next(request)
