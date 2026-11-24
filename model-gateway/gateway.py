# model-gateway/gateway.py
"""
vLLM API Gateway —— 按 API key 路由推理请求。

配置来源：/etc/gateway/gateway.yaml（路由表，运行时 bind mount 挂载）
启动时读取，无需硬编码。

职责：
  - 校验请求的 Authorization: Bearer <key>
  - 根据 key 映射到对应的上游推理实例
  - 各上游只加载一个模型，无需 gateway 注入 model
  - 透传 OpenAI 兼容接口
  - 每个上游实例使用独立的 upstream_key，避免单密钥全局复用
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

logger = logging.getLogger("gateway")

# ── 固定配置 ──────────────────────────────────────────────────────
_CONFIG_PATH = "/etc/gateway/gateway.yaml"
_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MiB
_DEFAULT_TIMEOUT_SECONDS = 30

# api_key → {upstream, upstream_key}
ROUTING_TABLE: dict[str, dict[str, str]] = {}

# ── 共享连接池 ────────────────────────────────────────────────────
_http_client: httpx.AsyncClient | None = None


def _load_config() -> None:
    """从 gateway.yaml 加载路由表（含每实例独立 upstream_key）。"""
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(f"网关配置文件不存在: {_CONFIG_PATH}")

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        raise TypeError(f"配置格式错误，根节点必须是映射: {_CONFIG_PATH}")

    routes = cfg.get("routes")
    if not isinstance(routes, dict) or not routes:
        raise ValueError(f"配置格式错误，缺少 routes: {_CONFIG_PATH}")

    loaded_routes: dict[str, dict[str, str]] = {}
    for route_index, (api_key, route_cfg) in enumerate(routes.items(), start=1):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("路由配置中的 api_key 必须是非空字符串")
        api_key = api_key.strip()
        if api_key in loaded_routes:
            raise ValueError("路由配置中的 api_key 去除首尾空格后重复")
        if not isinstance(route_cfg, dict):
            raise TypeError(f"第 {route_index} 条路由配置必须是映射")

        upstream = route_cfg.get("upstream")
        upstream_key = route_cfg.get("upstream_key")
        if not isinstance(upstream, str) or not upstream.strip():
            raise ValueError(f"第 {route_index} 条路由缺少有效的 upstream")
        upstream = upstream.strip().rstrip("/")
        parsed_upstream = urlsplit(upstream)
        if (
            parsed_upstream.scheme not in {"http", "https"}
            or not parsed_upstream.netloc
            or parsed_upstream.username
            or parsed_upstream.password
            or parsed_upstream.query
            or parsed_upstream.fragment
        ):
            raise ValueError(
                f"第 {route_index} 条路由的 upstream 必须是有效的 HTTP(S) 基础地址"
            )
        if not isinstance(upstream_key, str) or not upstream_key.strip():
            raise ValueError(
                f"第 {route_index} 条路由缺少 upstream_key，"
                "每个实例必须配置独立密钥（P0-4 安全要求）"
            )

        loaded_routes[api_key] = {
            "upstream": upstream,
            "upstream_key": upstream_key.strip(),
        }

    ROUTING_TABLE.clear()
    ROUTING_TABLE.update(loaded_routes)


_load_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时创建共享连接池，关闭时释放。"""
    global _http_client
    _http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        timeout=_DEFAULT_TIMEOUT_SECONDS,
    )
    try:
        yield
    finally:
        client = _http_client
        _http_client = None
        if client is not None:
            await client.aclose()


# SECURITY: P1-24 FastAPI 默认暴露 /docs (Swagger UI) + /redoc，泄露路由/schema/版本信息。
# 当前仅 ai-network 内网可达，风险可控。
# 上公网前：加 docs_url=None, redoc_url=None，并新增 /health 端点替换 healthcheck 探测。
app = FastAPI(title="vLLM Gateway", version="1.0", lifespan=lifespan)


# SECURITY: P1-25 网关无速率限制，单 key 可无限请求耗尽 GPU。
# 当前可接受：
#   - 仅 ai-network 内网可达，唯一调用方为 app-server（已有 slowapi 12 端点限速）
#   - vLLM 有 max_num_seqs 队列兜底，Ollama 单模型串行，不雪崩
#   - 拿到 upstream_key = 已突破容器/宿主机，此时限速亦无效
# 上公网 / 多租户前加 per-key 限速（slowapi 或 token bucket）。
def _extract_api_key(request: Request) -> str | None:
    """从 Authorization header 提取 Bearer token。"""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def _read_request_body(request: Request) -> bytes:
    """在读取时限制请求体大小，避免超限请求先被完整缓冲到内存。"""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_BODY_SIZE:
                raise HTTPException(status_code=413, detail="请求体过大")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="无效的 Content-Length"
            ) from None

    chunks: list[bytes] = []
    total_size = 0
    async for chunk in request.stream():
        total_size += len(chunk)
        if total_size > _MAX_BODY_SIZE:
            raise HTTPException(status_code=413, detail="请求体过大")
        chunks.append(chunk)
    return b"".join(chunks)


def _build_target_url(upstream_base: str, request: Request) -> str:
    target_url = f"{upstream_base}{request.url.path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    return target_url


def _build_upstream_headers(request: Request, upstream_key: str) -> dict[str, str]:
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    headers.pop("authorization", None)
    headers["Authorization"] = f"Bearer {upstream_key}"
    return headers


def _is_stream_request(method: str, body: bytes) -> bool:
    if method != "POST" or not body:
        return False
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("stream") is True


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    connection_tokens = {
        value.strip().lower()
        for value in headers.get("connection", "").split(",")
        if value.strip()
    }
    excluded_headers = {
        "connection",
        "content-encoding",
        "content-length",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    } | connection_tokens
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in excluded_headers
    }


async def _forward_stream(
    client: httpx.AsyncClient,
    request: Request,
    target_url: str,
    body: bytes,
    upstream_headers: dict[str, str],
    upstream_base: str,
) -> StreamingResponse:
    """建立上游流式响应，并透传状态、响应头和响应体。"""
    try:
        upstream_request = client.build_request(
            method=request.method,
            url=target_url,
            content=body,
            headers=upstream_headers,
        )
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="上游服务超时") from None
    except httpx.HTTPError as exc:
        logger.warning(
            "流式上游请求失败 | upstream=%s | error_type=%s",
            upstream_base,
            type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="上游服务异常") from None

    response_headers = _filter_response_headers(upstream_response.headers)
    is_sse_response = "text/event-stream" in upstream_response.headers.get(
        "content-type", ""
    ).lower()

    async def stream_generator():
        try:
            try:
                async for chunk in upstream_response.aiter_bytes():
                    yield chunk
            except httpx.TimeoutException:
                logger.warning(
                    "流式上游读取超时 | upstream=%s | path=%s",
                    upstream_base,
                    request.url.path,
                )
                if is_sse_response:
                    yield 'event: error\ndata: {"type":"upstream_timeout","message":"上游服务响应超时，请重试"}\n\n'.encode()
            except httpx.HTTPError as exc:
                logger.warning(
                    "流式上游读取失败 | upstream=%s | error_type=%s",
                    upstream_base,
                    type(exc).__name__,
                )
                if is_sse_response:
                    yield 'event: error\ndata: {"type":"upstream_error","message":"上游服务异常"}\n\n'.encode()
            except Exception:
                logger.exception(
                    "流式转发未知异常 | upstream=%s | path=%s",
                    upstream_base,
                    request.url.path,
                )
                if is_sse_response:
                    yield 'event: error\ndata: {"type":"gateway_error","message":"网关内部错误"}\n\n'.encode()
        finally:
            await upstream_response.aclose()

    return StreamingResponse(
        stream_generator(),
        status_code=upstream_response.status_code,
        headers=response_headers,
        background=BackgroundTask(upstream_response.aclose),
    )


async def _forward_buffered(
    client: httpx.AsyncClient,
    request: Request,
    target_url: str,
    body: bytes,
    upstream_headers: dict[str, str],
    upstream_base: str,
) -> Response:
    """转发普通请求，失败时返回合适的网关错误状态码。"""
    upstream_response: httpx.Response | None = None
    for attempt in range(2):
        try:
            upstream_response = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=upstream_headers,
            )
            break
        except httpx.ConnectError as exc:
            logger.warning(
                "上游连接失败 | upstream=%s | attempt=%s | error_type=%s",
                upstream_base,
                attempt + 1,
                type(exc).__name__,
            )
            if attempt == 0:
                continue
            raise HTTPException(status_code=502, detail="上游服务不可达") from None
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="上游服务超时") from None
        except httpx.HTTPError as exc:
            logger.warning(
                "上游请求失败 | upstream=%s | error_type=%s",
                upstream_base,
                type(exc).__name__,
            )
            raise HTTPException(status_code=502, detail="上游服务异常") from None

    if upstream_response is None:
        raise HTTPException(status_code=502, detail="上游服务异常")

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=_filter_response_headers(upstream_response.headers),
    )


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy(request: Request):
    """全路径透传代理。"""

    client = _http_client
    if client is None:
        raise HTTPException(status_code=503, detail="网关未就绪")

    api_key = _extract_api_key(request)
    if not api_key or api_key not in ROUTING_TABLE:
        raise HTTPException(status_code=401, detail="无效的 API key")

    route = ROUTING_TABLE[api_key]
    upstream_base = route["upstream"]
    target_url = _build_target_url(upstream_base, request)
    body = await _read_request_body(request)
    upstream_headers = _build_upstream_headers(request, route["upstream_key"])

    if _is_stream_request(request.method, body):
        return await _forward_stream(
            client,
            request,
            target_url,
            body,
            upstream_headers,
            upstream_base,
        )

    return await _forward_buffered(
        client,
        request,
        target_url,
        body,
        upstream_headers,
        upstream_base,
    )
