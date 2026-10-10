# app-server/src/com/damon/ming/encryption/__init__.py
"""
纯加密原语模块 —— 零 HTTP 依赖，可独立移植。

提供：
  - AES-256-GCM 对称加密（crypto_engine.AesGcmEngine）
  - RSA-OAEP 非对称加密（crypto_engine.RsaEngine）
  - 统一加密入口（crypto_engine.CryptoEngine，按 CipherSuite 分发）
  - 密钥生命周期管理（key_management.KeyManager，含会话密钥 + 数据密钥 + 盲索引密钥）
  - HMAC-SHA256 请求签名（signature）
  - 加密套件枚举（cipher_suite.CipherSuite）
  - 数据库字段加解密（field_encryptor.FieldEncryptor）
  - 密钥存储后端抽象（key_store/，含 BaseKeyStore / MemoryKeyStore）

不提供（它们属于 HTTP 业务层）：
  - PostgreSQL 存储实现 → 见 router/encryption/pg_key_store.py
  - 中间件 → 见 middleware/encryption_middleware.py
  - 路由 → 见 router/encryption/encryption_router.py
"""

from src.com.damon.ming.encryption.cipher_suite import CipherSuite
from src.com.damon.ming.encryption.crypto_engine import (
    AesGcmEngine,
    CryptoEngine,
    EncryptedPayload,
    RsaEngine,
)
from src.com.damon.ming.encryption.encryption_config_loader import (
    EncryptionConfig,
    EncryptionConfigLoader,
)
from src.com.damon.ming.encryption.field_encryptor import FieldEncryptor
from src.com.damon.ming.encryption.key_management import KeyManager, SessionKey
from src.com.damon.ming.encryption.signature import verify_signature

__all__ = [
    "AesGcmEngine",
    "CipherSuite",
    "CryptoEngine",
    "EncryptedPayload",
    "EncryptionConfig",
    "EncryptionConfigLoader",
    "FieldEncryptor",
    "KeyManager",
    "RsaEngine",
    "SessionKey",
    "verify_signature",
]
