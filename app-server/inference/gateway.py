"""
vLLM API Gateway —— 按 API key 路由推理请求。

配置来源：inference/gateway.yaml（路由表）
启动时读取，无需硬编码。

职责：
  - 校验请求的 Authorization: Bearer <key>
  - 根据 key 映射到对应的上游推理实例
  - 各上游只加载一个模型，无需 gateway 注入 model
  - 透传 OpenAI 兼容接口
"""

import os

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

# ── 配置路径 ──────────────────────────────────────────────────────
_CONFIG_PATH = os.environ.get(
    "GATEWAY_CONFIG_PATH",
    "/etc/gateway/gateway.yaml",
)

ROUTING_TABLE: dict[str, str] = {}  # api_key → upstream_base
UPSTREAM_KEY: str = "akUpstream"


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

app = FastAPI(title="vLLM Gateway", version="1.0")


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

    api_key = _extract_api_key(request)
    if not api_key or api_key not in ROUTING_TABLE:
        raise HTTPException(status_code=401, detail="无效的 API key")

    upstream_base = ROUTING_TABLE[api_key]

    target_url = f"{upstream_base}{request.url.path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    body = await request.body()

    upstream_headers = dict(request.headers)
    upstream_headers.pop("host", None)
    upstream_headers.pop("authorization", None)
    upstream_headers["Authorization"] = f"Bearer {UPSTREAM_KEY}"

    is_stream = False
    if request.method == "POST" and body:
        try:
            import json

            is_stream = json.loads(body).get("stream", False)
        except Exception:
            pass

    timeout_seconds = float(os.environ.get("GATEWAY_TIMEOUT", "180"))

    if is_stream:

        async def stream_generator():
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                async with client.stream(
                    method=request.method,
                    url=target_url,
                    content=body,
                    headers=upstream_headers,
                ) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=upstream_headers,
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=502, detail=f"上游服务不可达: {upstream_base}"
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="上游服务超时")

    excluded_headers = {"transfer-encoding", "connection"}
    response_headers = {
        k: v for k, v in resp.headers.items() if k.lower() not in excluded_headers
    }

    return JSONResponse(
        content=resp.json()
        if resp.headers.get("content-type", "").startswith("application/json")
        else resp.text,
        status_code=resp.status_code,
        headers=response_headers,
    )
