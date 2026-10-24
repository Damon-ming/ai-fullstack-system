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
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.schemas.response import BaseBizFailedData, BaseFailedResponse

logger = pin("rate_limiter")


# 可信反向代理 IP 列表。仅当直连对端 IP 在此列表中时才解析 X-Forwarded-For，
# 否则直接使用 TCP peer IP 作为限流键（防客户端伪造 header 绕过限流）。
# Nginx 与 uvicorn 同机部署，回环地址为可信代理 → 读取 X-Forwarded-For 取真实客户端 IP。
# 配置时只填实际代理 IP，切勿填 0.0.0.0/0 或 ::/0 否则客户端可伪造 header 绕过限流。
#
# TODO: 当前部署为 Host nginx + Docker app-server，nginx 通过 127.0.0.1:8000 转发到容器，
#  但 uvicorn 看到的 peer IP 是 Docker 网桥 IP（如 172.17.0.1），不是 127.0.0.1。
#  导致 TRUSTED_PROXIES 匹配失败，所有用户共享同一限流键（Docker 网关 IP），per-IP 限流失效。
#
#  修复方案（任选其一）：
#    A. TRUSTED_PROXIES 改为环境变量读取，docker-compose 中配置 Docker 网桥 IP
#    B. nginx 容器化，与 app-server 在同一 Docker 自定义网络，固定 nginx 容器 IP 后写入此处
#    C. 给 nginx 容器配置固定 IP（ipv4_address），TRUSTED_PROXIES 写该固定 IP
#
#  优先级：P2（功能可用但限流粒度变粗，不影响核心业务）
TRUSTED_PROXIES: set[str] = {"127.0.0.1"}


def _rate_limit_key(request: Request) -> str:
    """获取客户端真实 IP 用于限流。

    仅在可信反向代理后方时解析 X-Forwarded-For（取最左侧原始客户端 IP），
    否则直接使用 TCP peer IP，避免客户端伪造 header 绕过限流配额。
    """
    peer_ip = request.client.host if request.client else "unknown"
    if peer_ip in TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # 格式: "client, proxy1, proxy2" — 最左侧是原始客户端
            client_ip = forwarded.split(",")[0].strip()
            if client_ip:
                return client_ip

    return peer_ip


# per-IP 限流（默认内存存储，多实例部署时切换为 Redis）
# 注意：NAT 环境（公司/校园网）下多用户共享同一公网 IP 会共享限流配额。
# per-user 限流需认证后执行，当前部署规模小 IP 限流足够，优先级 P3。
# TODO: 多 worker 部署时切换为 Redis 存储，确保全局限流一致
#  依赖: pip install redis
#  配置: storage_uri="redis://localhost:6379"
#  优先级: P2，单实例部署内存模式即可
limiter = Limiter(
    key_func=_rate_limit_key,
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
        content=BaseFailedResponse(
            code=ErrorCode.SYSTEM.RATE_LIMITED,
            data=BaseBizFailedData(error_msg=t(I18nKey.RATE_LIMITED)),
        ).model_dump(),
    )
