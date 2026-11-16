"""游标载荷的 URL-safe Base64 + JSON 编解码。"""

import base64
import binascii
import json


class CursorCodecError(ValueError):
    """游标载荷无法解码为 JSON 对象。"""


def encode_cursor_payload(payload: dict[str, object]) -> str:
    """将游标字段编码为 URL-safe 字符串。"""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor_payload(cursor: str) -> dict[str, object]:
    """解码游标载荷；字段和值的业务校验由调用方负责。"""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("游标载荷必须是 JSON 对象")
        return payload
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        raise CursorCodecError("游标编码无效") from exc
