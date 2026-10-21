# app-server/src/com/damon/ming/encryption/v1/__init__.py
"""
加密协议 v1 实现 —— AES-256-GCM + RSA-OAEP + HMAC-SHA256。

包含：
  - CipherSuite 加密套件枚举
  - AesGcmEngine / RsaEngine / CryptoEngine 加解密引擎
  - RSAKeyPair RSA 密钥对管理（纯技术）
  - SessionKey 会话密钥数据模型（纯数据）
  - KeyMaterial 数据密钥 + 盲索引密钥管理（纯技术）
  - verify_signature HMAC-SHA256 签名验证
  - FieldEncryptor 数据库字段加解密

v2 协议实现见 encryption/v2/，接口签名以此为准。
"""

from src.com.damon.ming.encryption.v1.cipher_suite import CipherSuite
from src.com.damon.ming.encryption.v1.crypto_engine import (
    ENCRYPTION_VERSION,
    AesGcmEngine,
    CryptoEngine,
    EncryptedPayload,
    RsaEngine,
)
from src.com.damon.ming.encryption.v1.field_encryptor import FieldEncryptor
from src.com.damon.ming.encryption.v1.key_management import KeyMaterial, SessionKey
from src.com.damon.ming.encryption.v1.rsa_key_pair import RSAKeyPair
from src.com.damon.ming.encryption.v1.signature import verify_signature

__all__ = [
    "ENCRYPTION_VERSION",
    "AesGcmEngine",
    "CipherSuite",
    "CryptoEngine",
    "EncryptedPayload",
    "FieldEncryptor",
    "KeyMaterial",
    "RSAKeyPair",
    "RsaEngine",
    "SessionKey",
    "verify_signature",
]
