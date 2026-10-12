# app-server/src/com/damon/ming/middleware/context_middleware.py
"""
请求上下文中间件 —— 在请求链路最前端解析所有头部，统一放入 request.state.ctx。

后续中间件和路由通过 request.state.ctx 读取头部数据，不再直接访问 request.headers。

注册顺序：必须是第一个中间件（在 encryption / auth 之前）。
"""

from src.com.damon.ming.middleware.request_context import build_request_context
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class ContextMiddleware(BaseHTTPMiddleware):
    """请求上下文中间件 —— 一次性解析所有头部。"""

    async def dispatch(self, request: Request, call_next):
        # 一次性提取所有头部 → 存入 request.state.ctx
        request.state.ctx = build_request_context(request)
        return await call_next(request)
