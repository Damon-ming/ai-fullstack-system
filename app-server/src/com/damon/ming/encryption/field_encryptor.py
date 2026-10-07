# app-server/src/com/damon/ming/encryption/field_encryptor.py
"""
数据库字段加解密

将加密 / 解密能力封装到单个字符串，直接存入数据库 VARCHAR/TEXT 列。
密文格式：base64( version_byte + key_id_len + key_id + nonce + ciphertext )

支持两种模式（通过 CipherSuite 选择）：
  - DATABASE_AES_GCM:      随机 nonce，每次结果不同（默认，最安全）
  - DATABASE_DETERMINISTIC: 派生 nonce，相同明文→相同密文（可等值查询）

性能考虑：
  - AES-GCM 在 Python cryptography 库中是 C 实现，单字段 < 1ms
  - 批量操作（如导出）考虑用 C-extension 或 Rust 重写为可选优化

典型用法：
    # Model 层
    class User(Base):
        phone_enc = Column(String(512))     # 加密存储
        phone_idx = Column(String(32))      # 盲索引，用于查询

    # 写入
    user.phone_enc = FieldEncryptor.encrypt(phone, CipherSuite.DATABASE_AES_GCM)
    user.phone_idx = FieldEncryptor.blind_index(phone)

    # 读取
    phone = FieldEncryptor.decrypt(user.phone_enc)

    # 查询
    db.query(User).filter(User.phone_idx == FieldEncryptor.blind_index("13800000000"))
"""

import base64
import struct

from src.com.damon.ming.encryption.cipher_suite import CipherSuite
from src.com.damon.ming.encryption.crypto_engine import (
    CryptoEngine,
    EncryptedPayload,
)

# ---------------------------------------------------------------------------
# 版本与格式
# ---------------------------------------------------------------------------

FORMAT_VERSION = 0x01  # 密文格式版本，预留给未来升级


def _pack_ciphertext(key_id: str, nonce: bytes, ciphertext: bytes) -> str:
    """
    将 key_id + nonce + ciphertext 打包成单个 base64 字符串。

    格式（打包前）：
      [version:1][key_id_len:1][key_id:variable][nonce:variable][ciphertext:variable]

    所有长度用大端 uint8（key_id_len ≤ 255 字节，足够用了）。
    """
    key_id_bytes = key_id.encode("utf-8")
    if len(key_id_bytes) > 255:
        raise ValueError(f"key_id too long: {len(key_id_bytes)} bytes (max 255)")

    packed = (
        struct.pack("!B", FORMAT_VERSION)
        + struct.pack("!B", len(key_id_bytes))
        + key_id_bytes
        + nonce
        + ciphertext
    )
    return base64.b64encode(packed).decode("ascii")


def _unpack_ciphertext(packed_b64: str) -> tuple[str, bytes, bytes]:
    """从 base64 字符串解包出 (key_id, nonce, ciphertext)。"""
    raw = base64.b64decode(packed_b64)
    offset = 0

    version = raw[offset]
    offset += 1
    if version != FORMAT_VERSION:
        raise ValueError(f"Unsupported ciphertext format version: {version}")

    key_id_len = raw[offset]
    offset += 1

    key_id = raw[offset : offset + key_id_len].decode("utf-8")
    offset += key_id_len

    # nonce 固定 12 字节（AES-GCM）
    from src.com.damon.ming.encryption.crypto_engine import AES_NONCE_SIZE

    nonce = raw[offset : offset + AES_NONCE_SIZE]
    offset += AES_NONCE_SIZE

    ciphertext = raw[offset:]

    return key_id, nonce, ciphertext


# ---------------------------------------------------------------------------
# FieldEncryptor — 字段级加解密
# ---------------------------------------------------------------------------


class FieldEncryptor:
    """
    数据库字段加解密工具类。

    与 AesGcmEngine 的区别：
      - AesGcmEngine 返回结构化 EncryptedPayload，适合网络传输
      - FieldEncryptor 返回单个 base64 字符串，适合存入数据库单列
    """

    @staticmethod
    def encrypt(
        plaintext: str,
        suite: CipherSuite = CipherSuite.DATABASE_AES_GCM,
        *,
        key: bytes | None = None,
        key_id: str = "data-key-v1",
        index_key: bytes | None = None,
    ) -> str:
        """
        加密数据库字段，返回可直接存入 VARCHAR 列的 base64 字符串。

        参数：
          plaintext:  待加密明文
          suite:       加密套件（默认随机 nonce，最安全）
          key:         AES-256 密钥（32 字节），为 None 时尝试从 KeyManager 取
          key_id:      密钥标识（写入密文，解密时用于取对应密钥）
          index_key:   盲索引密钥（可选，传则同时返回索引）

        返回：
          密文字符串。
        """
        from src.com.damon.ming.encryption.globals import get_key_manager

        if key is None:
            key = get_key_manager().get_data_key(key_id)

        plaintext_bytes = plaintext.encode("utf-8")

        if suite == CipherSuite.DATABASE_DETERMINISTIC:
            payload = CryptoEngine.encrypt(plaintext_bytes, key, suite)
        else:
            payload = CryptoEngine.encrypt(
                plaintext_bytes, key, CipherSuite.DATABASE_AES_GCM
            )

        return _pack_ciphertext(
            key_id=payload.key_id or key_id,
            nonce=base64.b64decode(payload.nonce),
            ciphertext=base64.b64decode(payload.encrypted),
        )

    @staticmethod
    def decrypt(
        packed_b64: str,
        suite: CipherSuite = CipherSuite.DATABASE_AES_GCM,
        *,
        key_map: dict[str, bytes] | None = None,
    ) -> str:
        """
        解密数据库字段。

        参数：
          packed_b64: FieldEncryptor.encrypt 返回的密文
          suite:       加密套件（需与加密时一致）
          key_map:      key_id → key 的映射（为 None 时从 KeyManager 取）

        返回：
          解密后的明文字符串。
        """
        from src.com.damon.ming.encryption.globals import get_key_manager

        key_id, nonce, ciphertext = _unpack_ciphertext(packed_b64)

        if key_map and key_id in key_map:
            key = key_map[key_id]
        else:
            km = get_key_manager()
            key = km.get_data_key(key_id)

        payload = EncryptedPayload(
            encrypted=base64.b64encode(ciphertext).decode("ascii"),
            nonce=base64.b64encode(nonce).decode("ascii"),
            key_id=key_id,
        )

        plaintext_bytes = CryptoEngine.decrypt(payload, key, suite)
        return plaintext_bytes.decode("utf-8")

    @staticmethod
    def blind_index(value: str, index_key: bytes | None = None) -> str:
        """
        生成盲索引 token。

        用法：
          # 写入时
          user.email_idx = FieldEncryptor.blind_index(user.email)

          # 查询时
          db.query(User).filter(User.email_idx == FieldEncryptor.blind_index("foo@example.com"))
        """
        from src.com.damon.ming.encryption.globals import get_key_manager

        if index_key is None:
            index_key = get_key_manager().get_index_key()

        return CryptoEngine.blind_index(value, index_key)
