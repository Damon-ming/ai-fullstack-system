# app-server/src/com/damon/ming/encryption/__init__.py
"""
纯加密原语模块 —— 零 HTTP 依赖，零配置文件，可独立移植。

提供：
  - AES-256-GCM 对称加密（crypto_engine.AesGcmEngine）
  - RSA-OAEP 非对称加密（crypto_engine.RsaEngine）
  - 统一加密入口（crypto_engine.CryptoEngine，按 CipherSuite 分发）
  - 密钥生命周期管理（key_management.KeyManager，含会话密钥 + 数据密钥 + 盲索引密钥）
  - HMAC-SHA256 请求签名（signature）
  - 加密套件枚举（cipher_suite.CipherSuite）
  - 数据库字段加解密（field_encryptor.FieldEncryptor）
  - 密钥存储后端抽象（key_store/，含 BaseKeyStore / MemoryKeyStore）
  - 全局注入点（globals.py：set_key_manager / set_sign_context 等）

不提供（它们属于业务层 app/）：
  - 配置加载 → 见 app/config/encryption_config_loader.py
  - 数据库存储实现 → 见 router/encryption/key_store.py
  - 中间件 → 见 middleware/encryption_middleware.py
  - 路由 → 见 router/encryption/encryption_router.py
"""

from src.com.damon.ming.encryption.globals import SUPPORTED_ENCRYPTION_VERSIONS
from src.com.damon.ming.encryption.v1 import (
    ENCRYPTION_VERSION,
    AesGcmEngine,
    CryptoEngine,
    EncryptedPayload,
    FieldEncryptor,
    KeyManager,
    RsaEngine,
    SessionKey,
    verify_signature,
)

__all__ = [
    "ENCRYPTION_VERSION",
    "SUPPORTED_ENCRYPTION_VERSIONS",
    "AesGcmEngine",
    "CipherSuite",
    "CryptoEngine",
    "EncryptedPayload",
    "FieldEncryptor",
    "KeyManager",
    "RsaEngine",
    "SessionKey",
    "verify_signature",
]
