# app-server/src/com/damon/ming/encryption/signature.py
"""
请求签名验证工具 — HMAC-SHA256

与前端 computeSignature 对应：
  1. 取请求参数（排除 signature/timestamp/nonce），按 key 升序排序
  2. 拼接成 key1=v1&key2=v2 格式
  3. 加上 timestamp + nonce
  4. HMAC-SHA256(secret, 拼接串) → hex
  5. 与请求中的 signature 比对
"""

import hashlib
import hmac
import json
import time
from typing import Any

# 不参与签名的字段
SIGN_EXCLUDE_KEYS = {"signature", "timestamp", "nonce"}

# 时间戳容差：±5 分钟（防重放）
TIMESTAMP_TOLERANCE_MS = 5 * 60 * 1000


def verify_signature(
    params: dict[str, Any],
    secret: str,
    signature: str,
    timestamp: int,
    nonce: str,
) -> tuple[bool, str]:
    """
    验证请求签名。

    返回: (是否通过, 失败原因)
    """
    # 1. 时间戳检查（防重放）
    now = int(time.time() * 1000)
    if abs(now - timestamp) > TIMESTAMP_TOLERANCE_MS:
        return False, f"Timestamp expired: {timestamp} vs {now}"

    # 2. 排序并拼接业务参数
    sorted_keys = sorted(k for k in params if k not in SIGN_EXCLUDE_KEYS)
    parts = []
    for key in sorted_keys:
        val = params[key]
        if val is None:
            continue
        parts.append(f"{key}={_stringify_value(val)}")
    param_str = "&".join(parts)

    # 3. 加上 timestamp + nonce
    sign_content = f"{param_str}|ts={timestamp}|nonce={nonce}"

    # 4. HMAC-SHA256
    expected = hmac.new(
        secret.encode("utf-8"),
        sign_content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # 5. 比对（constant-time 比较防时序攻击）
    if not hmac.compare_digest(expected, signature):
        return False, "Signature mismatch"

    return True, ""


def _stringify_value(val: Any) -> str:
    """将参数值转为可签名的字符串"""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False, separators=(",", ":"))
    return str(val)
