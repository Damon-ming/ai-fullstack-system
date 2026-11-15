"""应用级异常处理器装配。"""

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from src.com.damon.ming.exception import register_exception_handler
from src.com.damon.ming.middleware.rate_limiter import rate_limit_handler


def register_app_exception_handlers(app: FastAPI) -> None:
    """集中注册应用通用异常处理器和限流异常处理器。"""
    register_exception_handler(app)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
