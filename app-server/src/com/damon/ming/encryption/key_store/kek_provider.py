# app-server/src/com/damon/ming/encryption/key_store/kek_provider.py
"""
KEK (Key Encryption Key) 提供者 —— 从环境变量派生加密密钥。

职责：
  - 从环境变量 MASTER_KEY 派生 KEK
  - 用 HKDF-SHA256 从主密钥 + salt 派生出固定长度的 AES-256 密钥
  - 用于加密存储到 DB 的 AES 会话密钥（加密后落盘）

安全要点：
  - MASTER_KEY 至少 32 字符，生产环境应使用强随机密钥
  - salt 固定（写在代码里），确保同一 MASTER_KEY 始终派生同一 KEK
  - KEK 只在内存中持有，不落盘

为什么不直接用 RSA 私钥加密？
  - RSA 私钥重启后会重新生成（当前实现），无法解密旧数据
  - KEK 从环境变量派生，只要 MASTER_KEY 不变，重启后仍能解密历史会话
"""

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# 固定 salt —— 确保同一 MASTER_KEY 始终派生同一 KEK
# 生产环境可以改为从环境变量读取，但固定值更便于运维
KEK_SALT = b"ming-ai-key-store-v1"
KEK_INFO = b"encryption-session-key-wrap"
KEK_LENGTH = 32  # AES-256


def derive_kek(master_key: str | None = None) -> bytes:
    """从 MASTER_KEY 环境变量派生 KEK。

    参数：
      master_key: 主密钥。为 None 时从 MASTER_KEY 环境变量读取。

    返回：
      32 字节 AES-256 密钥
    """
    if master_key is None:
        master_key = os.environ.get("MASTER_KEY", "")

    if not master_key:
        raise RuntimeError(
            "MASTER_KEY 环境变量未设置。请设置一个至少 32 字符的随机密钥。"
        )

    if len(master_key) < 16:
        import warnings
        warnings.warn(
            "MASTER_KEY 长度不足 32 字符，生产环境请使用更强的密钥",
            stacklevel=2,
        )

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEK_LENGTH,
        salt=KEK_SALT,
        info=KEK_INFO,
    )
    return hkdf.derive(master_key.encode("utf-8"))


def wrap_key(aes_key: bytes, kek: bytes) -> str:
    """用 KEK 加密 AES 会话密钥，返回 base64 编码的密文。

    格式与 crypto_engine.EncryptedPayload 一致：
      { "encrypted": base64, "nonce": base64 }

    使用 AES-256-GCM，每次加密随机生成 nonce。
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    ciphertext = AESGCM(kek).encrypt(nonce, aes_key, None)

    return base64.b64encode(nonce + ciphertext).decode("ascii")


def unwrap_key(wrapped_b64: str, kek: bytes) -> bytes:
    """解密 wrap_key 的结果，返回原始 AES 密钥字节。

    认证失败（密文被篡改 / KEK 错误）会抛出 InvalidTag。
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(wrapped_b64)
    nonce = raw[:12]
    ciphertext = raw[12:]

    return AESGCM(kek).decrypt(nonce, ciphertext, None)
