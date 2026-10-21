# app-server/src/com/damon/ming/encryption/key_store/__init__.py
"""
密钥存储工具 —— KEK 派生与密钥加解密原语（纯技术，可移植）。

提供：
  - derive_kek: 从业务配置注入的 salt/info 派生 Key Encryption Key
  - wrap_key:   用 KEK 加密 AES 密钥（存储前调用）
  - unwrap_key: 用 KEK 解密 AES 密钥（加载时调用）

存储后端接口和实现已迁移到 app/encryption/。
"""

from src.com.damon.ming.encryption.key_store.kek_provider import (
    derive_kek,
    unwrap_key,
    wrap_key,
)

__all__ = [
    "derive_kek",
    "unwrap_key",
    "wrap_key",
]
