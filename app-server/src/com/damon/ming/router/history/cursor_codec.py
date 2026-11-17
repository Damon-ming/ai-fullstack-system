# app-server/src/com/damon/ming/router/history/cursor_codec.py
"""通用游标载荷的 URL-safe Base64 + JSON 编解码。

这里只负责序列化和反序列化 JSON 对象，不定义游标字段，也不提供加密或
防篡改能力。各业务模块应在解码后自行校验载荷字段和值。
"""

import base64
import json


class CursorCodecError(ValueError):
    """游标无法解码为 JSON 对象。"""


def encode_cursor_payload(payload: dict[str, object]) -> str:
    """将 JSON 对象编码为不带填充符的 URL-safe Base64 字符串。"""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor_payload(cursor: str) -> dict[str, object]:
    """解码游标载荷；字段和值的业务校验由调用方负责。"""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("游标载荷必须是 JSON 对象")
        return payload
    except ValueError as exc:
        raise CursorCodecError("游标编码无效") from exc
