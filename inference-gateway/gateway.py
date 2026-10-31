# inference-gateway/gateway.py
"""
vLLM API Gateway —— 按 API key 路由推理请求。

配置来源：/etc/gateway/gateway.yaml（路由表，Dockerfile 构建时烘焙进镜像）
启动时读取，无需硬编码。

职责：
  - 校验请求的 Authorization: Bearer <key>
  - 根据 key 映射到对应的上游推理实例
  - 各上游只加载一个模型，无需 gateway 注入 model
  - 透传 OpenAI 兼容接口
"""

import json
import logging
import os
from contextlib import asynccontextmanager

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger("gateway")

# ── 配置路径 ──────────────────────────────────────────────────────
_CONFIG_PATH = os.environ.get(
    "GATEWAY_CONFIG_PATH",
    "/etc/gateway/gateway.yaml",
)
_MAX_BODY_SIZE = int(os.environ.get("GATEWAY_MAX_BODY_SIZE", "10485760"))  # 10MB

ROUTING_TABLE: dict[str, str] = {}  # api_key → upstream_base
UPSTREAM_KEY: str = "akUpstream"

# ── 共享连接池 ────────────────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None


def _load_config() -> None:
    """从 gateway.yaml 加载路由表。"""
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(f"网关配置文件不存在: {_CONFIG_PATH}")

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not cfg or "routes" not in cfg:
        raise ValueError(f"配置格式错误，缺少 routes: {_CONFIG_PATH}")

    global UPSTREAM_KEY
    UPSTREAM_KEY = cfg.get("upstream_key", "akUpstream")

    for api_key, route_cfg in cfg["routes"].items():
        upstream = route_cfg.get("upstream", "")
        if api_key and upstream:
            ROUTING_TABLE[api_key] = upstream


_load_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时创建共享连接池，关闭时释放。"""
    global _http_client
    _http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        timeout=float(os.environ.get("GATEWAY_TIMEOUT", "180")),
    )
    yield
    await _http_client.aclose()


app = FastAPI(title="vLLM Gateway", version="1.0", lifespan=lifespan)


def _extract_api_key(request: Request) -> str | None:
    """从 Authorization header 提取 Bearer token。"""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy(request: Request):
    """全路径透传代理。"""

    if _http_client is None:
        raise HTTPException(status_code=503, detail="网关未就绪")

    api_key = _extract_api_key(request)
    if not api_key or api_key not in ROUTING_TABLE:
        raise HTTPException(status_code=401, detail="无效的 API key")

    upstream_base = ROUTING_TABLE[api_key]

    target_url = f"{upstream_base}{request.url.path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    body = await request.body()
    if len(body) > _MAX_BODY_SIZE:
        raise HTTPException(status_code=413, detail="请求体过大")

    upstream_headers = dict(request.headers)
    upstream_headers.pop("host", None)
    upstream_headers.pop("content-length", None)
    upstream_headers.pop("authorization", None)
    upstream_headers["Authorization"] = f"Bearer {UPSTREAM_KEY}"

    is_stream = False
    if request.method == "POST" and body:
        try:
            is_stream = json.loads(body).get("stream", False)
        except Exception:
            pass

    if is_stream:

        async def stream_generator():
            try:
                async with _http_client.stream(
                    method=request.method,
                    url=target_url,
                    content=body,
                    headers=upstream_headers,
                ) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
            except (httpx.TimeoutException, httpx.ReadTimeout):
                logger.warning(
                    "流式上游超时 | upstream=%s | path=%s",
                    upstream_base,
                    request.url.path,
                )
                yield 'event: error\ndata: {"type":"upstream_timeout","message":"上游服务响应超时，请重试"}\n\n'.encode()
            except httpx.HTTPError as e:
                logger.warning(
                    "流式上游异常 | upstream=%s | error=%s", upstream_base, e
                )
                yield f'event: error\ndata: {{"type":"upstream_error","message":"{e!s}"}}\n\n'.encode()
            except Exception as e:
                logger.error(
                    "流式转发未知异常 | upstream=%s | error=%s", upstream_base, e
                )
                yield 'event: error\ndata: {"type":"gateway_error","message":"网关内部错误"}\n\n'.encode()

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    # 非流式：连接失败时重试 1 次
    for attempt in range(2):
        try:
            resp = await _http_client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=upstream_headers,
            )
            break
        except httpx.ConnectError:
            if attempt == 0:
                continue
            raise HTTPException(
                status_code=502, detail=f"上游服务不可达: {upstream_base}"
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="上游服务超时")

    excluded_headers = {"transfer-encoding", "connection", "content-length"}
    response_headers = {
        k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers
    }

    content_type = resp.headers.get("content-type", "")
    try:
        content = resp.json() if "json" in content_type else resp.text
    except Exception:
        content = resp.text

    return JSONResponse(
        content=content,
        status_code=resp.status_code,
        headers=response_headers,
    )
