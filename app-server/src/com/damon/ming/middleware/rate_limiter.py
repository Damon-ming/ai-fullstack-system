# app-server/src/com/damon/ming/middleware/rate_limiter.py
"""
速率限制器 —— slowapi 封装，per-IP 限流。

用法：
    from src.com.damon.ming.middleware.rate_limiter import limiter

    @router.post("/send/v1")
    @limiter.limit("10/minute")
    async def chat(req: Request, body: ChatRequest): ...

注册到 app（在 main.py 中）：
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

支持扩展：切换 Redis 存储只需修改 storage_uri，业务代码零改动。
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from src.com.damon.ming.log import pin

logger = pin("rate_limiter")

# per-IP 限流（默认内存存储，多实例部署时切换为 Redis）
limiter = Limiter(
    key_func=lambda request: request.client.host if request.client else "unknown",
    default_limits=["20/minute"],
    storage_uri="memory://",
)


# 429 响应处理器
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(
        "速率限制触发 | client=%s | path=%s",
        request.client.host if request.client else "unknown",
        request.url.path,
    )
    return JSONResponse(
        status_code=429,
        content={"code": 429, "error_msg": "请求过于频繁，请稍后再试"},
    )
