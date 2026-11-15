# app-server/src/com/damon/ming/middleware/rate_limiter.py
"""
速率限制器 —— slowapi 封装，per-IP 限流。

用法：
    from src.com.damon.ming.middleware.rate_limiter import limiter

    @router.post("/rag/answer/v1")
    @limiter.limit("10/minute")
    async def chat(request: Request, body: ChatRequest): ...

注册到 app（在 main.py 中）：
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

支持扩展：切换 Redis 存储只需修改 storage_uri，业务代码零改动。
"""

import ipaddress

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from src.com.damon.ming.app.config.env import get_trusted_proxy_networks
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.schemas.response import BaseBizFailedData, BaseFailedResponse

logger = pin("rate_limiter")


# 仅信任专用代理网络内的请求来源。Compose 中该网络只连接 web-app 与 app-server；
# Nginx 覆盖 X-Forwarded-For 后，才从该头读取客户端 IP。
TRUSTED_PROXY_NETWORKS = get_trusted_proxy_networks()


def _rate_limit_key(request: Request) -> str:
    """获取客户端真实 IP 用于限流。

    仅当 TCP peer 属于可信代理网段时才读取 X-Forwarded-For；否则使用 peer IP。
    """
    peer_ip = request.client.host if request.client else "unknown"
    try:
        peer_address = ipaddress.ip_address(peer_ip)
    except ValueError:
        return peer_ip

    if any(peer_address in network for network in TRUSTED_PROXY_NETWORKS):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Nginx 设置为 $remote_addr，因此该值只包含代理实际看到的客户端 IP。
            client_ip = forwarded.strip()
            try:
                return str(ipaddress.ip_address(client_ip))
            except ValueError:
                pass

    return peer_ip


# per-IP 限流（默认内存存储，多实例部署时切换为 Redis）
# 注意：NAT 环境（公司/校园网）下多用户共享同一公网 IP 会共享限流配额。
# per-user 限流需认证后执行，当前部署规模小 IP 限流足够，优先级 P3。
# TODO: 多 worker 或多 app-server 副本部署时切换为 Redis 存储，确保全局限流一致
#  依赖: pip install redis
#  配置: storage_uri="redis://localhost:6379"
#  优先级: P2，单实例部署内存模式即可
limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["20/minute"],
    storage_uri="memory://",
)


# 429 响应处理器
async def rate_limit_handler(request: Request, _exc: RateLimitExceeded):
    logger.warning(
        "速率限制触发 | client=%s | path=%s",
        request.client.host if request.client else "unknown",
        request.url.path,
    )
    return JSONResponse(
        status_code=429,
        content=BaseFailedResponse(
            code=ErrorCode.SYSTEM.RATE_LIMITED,
            data=BaseBizFailedData(error_msg=t(I18nKey.RATE_LIMITED)),
        ).model_dump(),
    )
