# app-server/src/com/damon/ming/encryption/v1/signature.py
"""
请求签名验证工具 — HMAC-SHA256（纯算法，无业务绑定）。

协议（由调用方约定）：
  1. 取请求参数，按 key 升序排序
  2. 拼接成 key1=v1&key2=v2 格式
  3. 加上 timestamp + nonce
  4. HMAC-SHA256(secret, 拼接串) → hex
  5. 与请求中的 signature 比对

调用方通过 exclude_keys 参数指定不参与签名的字段，
通过 timestamp_tolerance_ms 参数指定时间戳容差。
"""

import hashlib
import hmac
import time
from typing import Any


def verify_signature(
    params: dict[str, Any],
    secret: str,
    signature: str,
    timestamp: int,
    nonce: str,
    *,
    exclude_keys: set[str] | None = None,
    timestamp_tolerance_ms: int = 5 * 60 * 1000,
) -> tuple[bool, str]:
    """
    验证请求签名。

    参数：
      params:               待签名的参数字典
      secret:               共享密钥
      signature:            待比对的签名值（hex）
      timestamp:            签名时间戳（毫秒）
      nonce:                签名随机数
      exclude_keys:         不参与签名的字段集合（由调用方约定）
      timestamp_tolerance_ms: 时间戳容差（毫秒），默认 ±5 分钟

    返回: (是否通过, 失败原因)
    """
    # 1. 时间戳检查（防重放）
    now = int(time.time() * 1000)
    if abs(now - timestamp) > timestamp_tolerance_ms:
        return False, f"Timestamp expired: {timestamp} vs {now}"

    # 2. 排序并拼接业务参数
    keys_to_exclude = exclude_keys or set()
    sorted_keys = sorted(k for k in params if k not in keys_to_exclude)
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
    import json

    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False, separators=(",", ":"))
    return str(val)
