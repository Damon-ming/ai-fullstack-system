# app-server/src/com/damon/ming/encryption/v1/signature.py
"""
请求签名验证工具 — HMAC-SHA256 + HKDF 密钥派生。

协议（由调用方约定）：
  1. 取请求参数，按 key 升序排序
  2. 拼接成 key1=v1&key2=v2 格式
  3. 加上 timestamp + nonce
  4. HMAC-SHA256(secret, 拼接串) → hex
  5. 与请求中的 signature 比对

签名密钥派生：
  - 不再使用全局共享密钥
  - 每个会话从 AES-256 主密钥通过 HKDF-SHA256 派生独立的签名密钥
  - 派生上下文由调用方从全局注入点获取，确保与前端一致
"""

import hashlib
import hmac
import time
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_signing_key(aes_key: bytes, sign_context: bytes) -> bytes:
    """
    从 AES-256 主密钥派生 HMAC 签名密钥。

    使用 HKDF-SHA256，context 由调用方传入（从全局注入点获取），
    确保前后端派生结果一致。
    派生出的 32 字节密钥直接用于 HMAC-SHA256 签名。

    参数：
      aes_key:       AES-256 主密钥（32 字节）
      sign_context:  HKDF info 参数，由业务层配置注入（encryption 模块不包含此常量）
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=sign_context,
    )
    return hkdf.derive(aes_key)


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
      secret:               签名密钥字符串（派生后的签名密钥，非 AES 主密钥）
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
