# app-server/src/com/damon/ming/encryption/field_encryptor.py
"""
数据库字段加解密

将加密 / 解密能力封装到单个字符串，直接存入数据库 VARCHAR/TEXT 列。
密文格式：base64( version_byte + nonce + ciphertext )

支持两种模式（通过 CipherSuite 选择）：
  - DATABASE_AES_GCM:      随机 nonce，每次结果不同（默认，最安全）
  - DATABASE_DETERMINISTIC: 派生 nonce，相同明文→相同密文（可等值查询）

性能考虑：
  - AES-GCM 在 Python cryptography 库中是 C 实现，单字段 < 1ms
  - 批量操作（如导出）考虑用 C-extension 或 Rust 重写为可选优化

典型用法：
    fe = FieldEncryptor(key_material)

    # 写入
    user.phone_enc = fe.encrypt(phone, CipherSuite.DATABASE_AES_GCM)
    user.phone_idx = fe.blind_index(phone)

    # 读取
    phone = fe.decrypt(user.phone_enc)

    # 查询
    db.query(User).filter(User.phone_idx == fe.blind_index("13800000000"))

密钥提供者由使用方构造并注入，本模块不依赖业务层的密钥管理实现。
"""

import base64
import struct
from abc import ABC, abstractmethod

from src.com.damon.ming.encryption.constants import (
    AES_NONCE_SIZE,
    CIPHERTEXT_FORMAT_VERSION,
)
from src.com.damon.ming.encryption.v1.cipher_suite import CipherSuite
from src.com.damon.ming.encryption.v1.crypto_engine import (
    CryptoEngine,
    EncryptedPayload,
)


class KeyProvider(ABC):
    """密钥提供者抽象接口，实现类必须显式继承并实现全部抽象方法。"""

    @abstractmethod
    def get_data_key(self) -> bytes: ...

    @abstractmethod
    def get_index_key(self) -> bytes: ...


def _pack_ciphertext(nonce: bytes, ciphertext: bytes) -> str:
    """
    将 nonce + ciphertext 打包成单个 base64 字符串。

    格式（打包前）：
      [version:1][nonce:固定长度][ciphertext:variable]
    """
    packed = (
        # 把 Python 的数字，打包成固定格式的二进制字节；或者把二进制字节解析回数字。
        # - `!`：**大端序（网络字节序）**，跨平台解析不会乱（Windows/Linux 解析一致）
        # - `B`：unsigned char，1 字节无符号整数，范围 0~255
        struct.pack("!B", CIPHERTEXT_FORMAT_VERSION) + nonce + ciphertext
    )
    return base64.b64encode(packed).decode("ascii")


def _unpack_ciphertext(packed_b64: str) -> tuple[bytes, bytes]:
    """从 base64 字符串解包出 (nonce, ciphertext)。"""
    raw = base64.b64decode(packed_b64)
    # 二进制是一整块连续流，没有分隔符。
    # 靠 offset 记录当前读取位置：版本 → nonce → 密文。
    offset = 0

    version = raw[offset]
    offset += 1
    if version != CIPHERTEXT_FORMAT_VERSION:
        raise ValueError(f"Unsupported ciphertext format version: {version}")

    nonce = raw[offset : offset + AES_NONCE_SIZE]
    offset += AES_NONCE_SIZE

    ciphertext = raw[offset:]

    return nonce, ciphertext


# ---------------------------------------------------------------------------
# FieldEncryptor — 字段级加解密
# ---------------------------------------------------------------------------


class FieldEncryptor:
    """
    数据库字段加解密器（构造时注入满足 KeyProvider 接口的对象）。

    与 AesGcmEngine 的区别：
      - AesGcmEngine 返回结构化 EncryptedPayload，适合网络传输
      - FieldEncryptor 返回单个 base64 字符串，适合存入数据库单列
    """

    def __init__(self, key_material: KeyProvider) -> None:
        if not isinstance(key_material, KeyProvider):
            raise TypeError("key_material 必须是 KeyProvider 的实现实例")
        self._key_material = key_material

    def encrypt(
        self,
        plaintext: str,
        suite: CipherSuite = CipherSuite.DATABASE_AES_GCM,
        *,
        key: bytes | None = None,
        index_key: bytes | None = None,
    ) -> str:
        """
        加密数据库字段，返回可直接存入 VARCHAR 列的 base64 字符串。

        参数：
          plaintext:  待加密明文
          suite:       加密套件（默认随机 nonce，最安全）
          key:         AES-256 密钥（32 字节），为 None 时从注入的密钥提供者取
          index_key:   盲索引密钥（可选，传则同时返回索引）

        返回：
          密文字符串。
        """
        if key is None:
            key = self._key_material.get_data_key()

        plaintext_bytes = plaintext.encode("utf-8")

        if suite == CipherSuite.DATABASE_DETERMINISTIC:
            payload = CryptoEngine.encrypt(plaintext_bytes, key, suite)
        else:
            payload = CryptoEngine.encrypt(
                plaintext_bytes, key, CipherSuite.DATABASE_AES_GCM
            )

        return _pack_ciphertext(
            nonce=base64.b64decode(payload.nonce),
            ciphertext=base64.b64decode(payload.encrypted),
        )

    def decrypt(
        self,
        packed_b64: str,
        suite: CipherSuite = CipherSuite.DATABASE_AES_GCM,
    ) -> str:
        """
        解密数据库字段。

        参数：
          packed_b64: FieldEncryptor.encrypt 返回的密文
          suite:       加密套件（需与加密时一致）

        返回：
          解密后的明文字符串。
        """
        nonce, ciphertext = _unpack_ciphertext(packed_b64)
        key = self._key_material.get_data_key()

        payload = EncryptedPayload(
            encrypted=base64.b64encode(ciphertext).decode("ascii"),
            nonce=base64.b64encode(nonce).decode("ascii"),
            key_id="",
        )

        plaintext_bytes = CryptoEngine.decrypt(payload, key, suite)
        return plaintext_bytes.decode("utf-8")

    def blind_index(self, value: str, index_key: bytes | None = None) -> str:
        """
        生成盲索引 token。

        用法：
          # 写入时
          user.email_idx = fe.blind_index(user.email)

          # 查询时
          db.query(User).filter(User.email_idx == fe.blind_index("foo@example.com"))
        """
        if index_key is None:
            index_key = self._key_material.get_index_key()

        return CryptoEngine.blind_index(value, index_key)
