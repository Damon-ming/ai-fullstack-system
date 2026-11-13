# app-server/src/com/damon/ming/middleware/encryption/wire.py
"""线格式判定与小工具（白名单 / 加密体 / 响应类型 / body 回写）。"""

from fastapi import Request
from starlette.responses import Response


def is_whitelisted(path: str, whitelist: tuple[str, ...]) -> bool:
    """前缀匹配白名单（路径级全放行，不区分方法）。"""
    return any(path.startswith(prefix) for prefix in whitelist)


def is_encrypted_body(body: dict) -> bool:
    """判断 body 是否符合加密协议（三个字段齐全且为字符串）。"""
    return (
        isinstance(body, dict)
        and isinstance(body.get("encrypted"), str)
        and isinstance(body.get("nonce"), str)
        and isinstance(body.get("keyId"), str)
    )


def is_json_response(response: Response) -> bool:
    """判断响应体是否为 JSON（决定是否整体加密响应）。

    必须读 content-type 头，不能用 response.media_type：
    BaseHTTPMiddleware 的 call_next 返回的是 _StreamingResponse，
    它只从下游拷贝 raw_headers，media_type 恒为 None。
    """
    return "application/json" in response.headers.get("content-type", "")


def is_event_stream_response(response: Response) -> bool:
    """判断响应是否为 SSE 流（决定是否逐事件加密）。"""
    return "text/event-stream" in response.headers.get("content-type", "")


def patch_request_body(request: Request, new_body: str) -> None:
    """把解密后的 body 写回请求,供下游路由读取。

    BaseHTTPMiddleware 用 _CachedRequest 包住请求,其 wrapped_receive 会优先
    返回 _body —— 下游 app 新建的 Request 从 receive 读到的就是这里写入的
    解密内容。只设 _body 即可,无需替换 body 方法(下游拿到的是另一个 Request
    对象,替换它的 body 方法不会生效)。
    """
    request._body = new_body.encode("utf-8")
