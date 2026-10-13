# app-server/src/com/damon/ming/middleware/request_context.py
"""
请求上下文 —— 所有头部数据在此收拢，避免各处散落读取 header。

设计：
  - 单次请求生命周期内，所有中间件 / 路由通过 request.state.ctx 获取头部数据
  - 不再直接调用 request.headers.get(...)
  - 新增头部字段只需在此处扩展 + 在 ContextMiddleware 中解析一次
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

from src.com.damon.ming.middleware.header_constants import (
    CLIENT_ENV,
    CLIENT_UA,
    DEVICE_ID,
    ENCRYPT_ENABLED,
    ENCRYPT_VERSION,
    SESSION_ID,
    SIGNATURE_VERSION,
    SYSTEM_VERSION,
)
from src.com.damon.ming.middleware.ua_fingerprint import parse_ua_header

# Token 提取时使用的 key 名（与前端约定一致）
TOKEN_COOKIE_NAME = "device_auth_token"


@dataclass
class RequestContext:
    """
    请求上下文 —— 一次性解析所有头部，后续统一从这里读取。

    使用方式：
        ctx = request.state.ctx
        if ctx.device_id: ...
    """

    # ---- 认证 ----
    token: str | None = None

    # ---- 设备 ----
    device_id: str = ""
    client_ua: str = ""
    ua_profile: object | None = None  # UAProfile，懒解析

    # ---- 会话（token + device 的唯一组合）----
    session_id: str = ""

    # ---- 加密 ----
    encrypt_enabled: bool = False
    encrypt_version: str = ""
    signature_version: str = ""

    # ---- 系统 ----
    system_version: str = ""
    client_env: str = ""

    # ---- 标准头 ----
    content_type: str = ""


def build_request_context(request: "Request") -> RequestContext:
    """
    从请求中一次性提取所有头部数据，构建 RequestContext。

    在中间件链最前端调用，后续所有组件通过 request.state.ctx 读取。
    """
    headers = request.headers

    # 加密相关
    encrypt_version = headers.get(ENCRYPT_VERSION, "")
    signature_version = headers.get(SIGNATURE_VERSION, "")
    encrypt_enabled = headers.get(ENCRYPT_ENABLED) == "1"

    # 设备 + UA
    device_id = headers.get(DEVICE_ID, "")
    client_ua = headers.get(CLIENT_UA, "")

    # 会话
    session_id = headers.get(SESSION_ID, "")

    # 系统
    system_version = headers.get(SYSTEM_VERSION, "")
    client_env = headers.get(CLIENT_ENV, "")

    # 标准头
    content_type = headers.get("content-type", "")

    # Token（Cookie / Authorization Bearer）
    token = _extract_token(headers)

    return RequestContext(
        token=token,
        device_id=device_id,
        client_ua=client_ua,
        ua_profile=None,  # 懒解析，需要时调用 parse_ua_header
        session_id=session_id,
        encrypt_enabled=encrypt_enabled,
        encrypt_version=encrypt_version,
        signature_version=signature_version,
        system_version=system_version,
        client_env=client_env,
        content_type=content_type,
    )


def _extract_token(headers) -> str | None:
    """从 headers 中提取 device_auth_token（Cookie / Authorization Bearer）。"""
    cookie_header = headers.get("cookie", "")
    if cookie_header:
        for pair in cookie_header.split(";"):
            pair = pair.strip()
            if pair.startswith(f"{TOKEN_COOKIE_NAME}="):
                return pair[len(TOKEN_COOKIE_NAME) + 1 :].strip()

    auth_header = headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None


def get_ua_profile(ctx: RequestContext):
    """懒解析 UAProfile（仅在需要时计算）。"""
    if ctx.ua_profile is None and ctx.client_ua:
        ctx.ua_profile = parse_ua_header(ctx.client_ua)
    return ctx.ua_profile
