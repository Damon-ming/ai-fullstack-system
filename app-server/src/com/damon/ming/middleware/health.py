# app-server/src/com/damon/ming/middleware/health.py
"""
存活探针中间件 —— 绕过 auth / encryption / rate limit，供 Docker 健康检查。

/ping 和 /health 直接返回 200，不经任何上层中间件。
Docker compose 通过 healthcheck 定期探测此端点判断容器是否就绪。
"""

# 不走中间件的路径前缀
_BYPASS_PATHS = ("/ping", "/health")

# 固定响应体
_RESPONSE_BODY = b'{"status":"ok"}'
_RESPONSE_HEADERS = [(b"content-type", b"application/json")]


def wrap_health_app(app):
    """将 ASGI app 包裹为带存活探针的最外层中间件。

    用法：
        app = FastAPI(...)
        ... 装配中间件和路由 ...
        app = wrap_health_app(app)
    """

    async def _middleware(scope, receive, send):
        if scope["type"] == "http" and scope["path"] in _BYPASS_PATHS:
            # 第一次 send → 发 HTTP 响应头（状态码 + Content-Type）
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": _RESPONSE_HEADERS,
                }
            )
            # 第二次 send → 发 HTTP 响应体（实际内容）
            await send(
                {
                    "type": "http.response.body",
                    "body": _RESPONSE_BODY,
                }
            )
            return
        await app(scope, receive, send)

    return _middleware
