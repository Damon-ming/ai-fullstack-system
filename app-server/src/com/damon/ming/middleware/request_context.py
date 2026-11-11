# app-server/src/com/damon/ming/middleware/request_context.py
"""
请求上下文 —— 所有头部数据在此收拢，避免各处散落读取 header。

设计：
  - 单次请求生命周期内，中间件 / 路由通过 request.state 的命名键获取头部数据
  - 不再直接调用 request.headers.get(...)
  - 新增头部字段只需在此处扩展 + 在 ContextMiddleware 中解析一次
  - 按语义分三组挂在 request.state 上：
      ctx        请求环境与通用头（UA / 版本 / 环境 / 类型 / 语言 / Content-Type）
      client     客户端身份（token / session_id / device_id）
      encryption 客户端声明的加密协议开关与版本
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

from src.com.damon.ming.middleware.header_constants import (
    APP_VERSION,
    CLIENT_ENV,
    CLIENT_TYPE,
    CLIENT_UA,
    DEVICE_ID,
    ENCRYPT_ENABLED,
    ENCRYPT_VERSION,
    LANGUAGE,
    SESSION_ID,
    SIGNATURE_VERSION,
)
from src.com.damon.ming.middleware.ua_fingerprint import UAProfile, parse_ua_header


@dataclass
class ClientContext:
    """
    客户端身份 —— 一次解析、请求内共享。

    使用方式：
        client = request.state.client
        if client.token: ...
    """

    # ---- 认证 ----
    token: str | None = None

    # ---- 会话（token + device 的唯一组合）----
    session_id: str = ""

    # ---- 设备 ----
    device_id: str = ""


@dataclass
class EncryptionContext:
    """
    加密上下文 —— 客户端声明的加密协议开关与版本。

    使用方式：
        enc = request.state.encryption
        if enc.enabled: ...
    """

    enabled: bool = False  # X-Encrypt-Enabled == "1"
    version: str = ""  # X-Encrypt-Version
    signature_version: str = ""  # X-Signature-Version


@dataclass
class RequestContext:
    """
    请求环境上下文 —— 客户端声明的工作环境 + 通用标准头。

    使用方式：
        ctx = request.state.ctx
        if "application/json" in ctx.content_type: ...
    """

    # ---- 标准头 ----
    content_type: str = ""

    # ---- 设备环境（X-Client-UA 摘要，构建时即解析）----
    ua: str = ""  # X-Client-UA 原始值
    ua_profile: UAProfile | None = None  # 解析后的环境摘要

    # ---- 客户端声明 ----
    app_version: str = ""
    env: int = 1  # 客户端环境：0 = debug，1 = release（默认 release）
    type: int = 0  # 客户端类型：0 = 浏览器，1 = 移动端
    language: str = ""  # X-Language 原始值（如 "zh-CN,en;q=0.9"），协商由 i18n 模块负责


def build_client_context(request: "Request") -> ClientContext:
    """解析客户端身份（token / session_id / device_id）。"""
    headers = request.headers
    return ClientContext(
        token=_extract_token(headers),
        session_id=headers.get(SESSION_ID, ""),
        device_id=headers.get(DEVICE_ID, ""),
    )


def build_encryption_context(request: "Request") -> EncryptionContext:
    """解析加密协议相关的头部（开关 + 版本）。"""
    headers = request.headers
    return EncryptionContext(
        enabled=headers.get(ENCRYPT_ENABLED) == "1",
        version=headers.get(ENCRYPT_VERSION, ""),
        signature_version=headers.get(SIGNATURE_VERSION, ""),
    )


def build_request_context(request: "Request") -> RequestContext:
    """解析请求环境与通用头部（UA / 版本 / 环境 / 类型 / 语言 / Content-Type）。"""
    headers = request.headers

    # 客户端环境：X-Client-Env 0 = debug, 1 = release（默认 release）
    client_env_raw = headers.get(CLIENT_ENV, "1")
    try:
        client_env = int(client_env_raw)
    except ValueError:
        client_env = 1
    # 客户端类型：X-Client-Type 0 = 浏览器, 1 = 移动端（默认浏览器）
    client_type_raw = headers.get(CLIENT_TYPE, "0")
    try:
        client_type = int(client_type_raw)
    except ValueError:
        client_type = 0

    ua = headers.get(CLIENT_UA, "")

    return RequestContext(
        content_type=headers.get("content-type", ""),
        ua=ua,
        ua_profile=parse_ua_header(ua) if ua else None,
        app_version=headers.get(APP_VERSION, ""),
        env=client_env,
        type=client_type,
        language=headers.get(LANGUAGE, ""),
    )


def _extract_token(headers) -> str | None:
    """从 Authorization Bearer 头中提取 device_auth_token。

    SECURITY: 仅支持 Authorization Bearer，不支持 Cookie 通道。
    消除双通道认证的 CSRF 攻击面和死代码风险（P1-2 修复）。

    TODO: 取得证书并部署 HTTPS 后，应迁移到 HttpOnly + Secure + SameSite=Strict Cookie：
      1. 前端删除 Authorization Bearer，启用 credentials: "same-origin"
      2. 登录端点改用 response.set_cookie(httponely=True, secure=True, samesite="strict")
      3. 本函数恢复 Cookie 读取（Authorization Bearer 作为 API 调用 fallback 保留）
      4. SSE 调用从 EventSource 迁移到 fetch + ReadableStream
    """
    auth_header = headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None
