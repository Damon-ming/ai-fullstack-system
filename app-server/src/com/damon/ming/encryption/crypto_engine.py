# app-server/src/com/damon/ming/encryption/crypto_engine.py
"""
加解密引擎

协议格式（加密后的 JSON body）：
{
  "encrypted": "<base64>",   // AES-GCM 密文（含 16 字节认证标签）
  "nonce": "<base64>",       // 12 字节随机 nonce
  "keyId": "<string>"        // 会话标识
}

AES-GCM 参数：
  - 密钥长度：256 bit（32 字节）
  - Nonce 长度：96 bit（12 字节），每次加密随机生成
  - 认证标签：128 bit（16 字节），由 cryptography 库自动附加在密文末尾
  - 附加认证数据（AAD）：当前为空，预留接口
"""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from src.com.damon.ming.encryption.cipher_suite import CipherSuite

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

AES_NONCE_SIZE = 12  # GCM 推荐 96 bit
AES_KEY_SIZE = 32  # AES-256


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EncryptedPayload:
    """加密后的载荷结构"""

    encrypted: str  # base64
    nonce: str  # base64
    key_id: str

    def to_dict(self) -> dict:
        return {
            "encrypted": self.encrypted,
            "nonce": self.nonce,
            "keyId": self.key_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ---------------------------------------------------------------------------
# AES-GCM 引擎
# ---------------------------------------------------------------------------


class AesGcmEngine:
    """
    AES-256-GCM 对称加解密。

    每次 encrypt 调用都会生成新的随机 nonce，
    调用方无需管理 nonce 状态。
    """

    @staticmethod
    def generate_key() -> bytes:
        """生成新的 AES-256 随机密钥。"""
        return AESGCM.generate_key(bit_length=256)

    @staticmethod
    def encrypt(
        plaintext: bytes, aes_key: bytes, aad: bytes | None = None
    ) -> tuple[bytes, bytes]:
        """
        加密数据。

        返回: (nonce, ciphertext_with_tag)
          - nonce: 12 字节，需随密文一起传输
          - ciphertext_with_tag: 密文 + 16 字节 GCM 认证标签
        """
        nonce = os.urandom(AES_NONCE_SIZE)
        aesgcm = AESGCM(aes_key)
        # encrypt 返回的 ciphertext 已包含末尾 16 字节 tag
        ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
        return nonce, ciphertext

    @staticmethod
    def decrypt(
        nonce: bytes,
        ciphertext_with_tag: bytes,
        aes_key: bytes,
        aad: bytes | None = None,
    ) -> bytes:
        """
        解密数据。

        认证失败（密文被篡改 / nonce 错误 / key 错误）会抛出 InvalidTag。
        """
        aesgcm = AESGCM(aes_key)
        return aesgcm.decrypt(nonce, ciphertext_with_tag, aad)

    # ---- 高层封装：直接操作 JSON 字符串 ------------------------------

    @classmethod
    def encrypt_json(
        cls, json_str: str, aes_key: bytes, key_id: str
    ) -> EncryptedPayload:
        """将 JSON 字符串加密为 EncryptedPayload。"""
        nonce, ciphertext = cls.encrypt(json_str.encode("utf-8"), aes_key)
        return EncryptedPayload(
            encrypted=base64.b64encode(ciphertext).decode("ascii"),
            nonce=base64.b64encode(nonce).decode("ascii"),
            key_id=key_id,
        )

    @classmethod
    def decrypt_payload(cls, payload: EncryptedPayload, aes_key: bytes) -> str:
        """将 EncryptedPayload 解密为原始 JSON 字符串。"""
        nonce = base64.b64decode(payload.nonce)
        ciphertext = base64.b64decode(payload.encrypted)
        plaintext = cls.decrypt(nonce, ciphertext, aes_key)
        return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# RSA 引擎（仅用于密钥交换阶段）
# ---------------------------------------------------------------------------


class RsaEngine:
    """RSA-OAEP 加解密，仅用于加密传输 AES 会话密钥。"""

    @staticmethod
    def encrypt_with_public_key(plaintext: bytes, public_key_pem: bytes) -> bytes:
        """使用 PEM 格式公钥加密（客户端侧模拟，服务端实际用私钥解密）。"""
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        pub_key = load_pem_public_key(public_key_pem)
        return pub_key.encrypt(
            plaintext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )


# ---------------------------------------------------------------------------
# 统一加密入口 — 按套件分发
# ---------------------------------------------------------------------------


class CryptoEngine:
    """
    统一加密入口，按 CipherSuite 分发到具体算法。

    用法：
        # 数据库字段（随机 nonce，不可查询）
        payload = CryptoEngine.encrypt(b"data", key, CipherSuite.DATABASE_AES_GCM)

        # 数据库字段（确定性，支持等值查询）
        payload = CryptoEngine.encrypt(b"data", key, CipherSuite.DATABASE_DETERMINISTIC)

        # 盲索引（生成查询 token）
        token = CryptoEngine.blind_index("phone", index_key)
    """

    @staticmethod
    def encrypt(
        plaintext: bytes,
        key: bytes,
        suite: CipherSuite,
        aad: bytes | None = None,
        nonce: bytes | None = None,
    ) -> EncryptedPayload:
        """
        按套件加密。

        参数：
          plaintext: 待加密数据
          key:        AES-256 密钥（32 字节）
          suite:      加密套件，决定算法组合
          aad:        附加认证数据（可选）
          nonce:      外部指定 nonce（仅 DATABASE_DETERMINISTIC 用，其他套件自动生成）

        返回：
          EncryptedPayload（key_id 为空，由调用方填充）
        """
        if suite == CipherSuite.DATABASE_AES_GCM:
            actual_nonce = nonce or os.urandom(AES_NONCE_SIZE)
            # encrypt 返回的是 (nonce, ciphertext)，但我们自己传了 nonce
            # 重新调用底层 AESGCM
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            ct = AESGCM(key).encrypt(actual_nonce, plaintext, aad)
            return EncryptedPayload(
                encrypted=base64.b64encode(ct).decode("ascii"),
                nonce=base64.b64encode(actual_nonce).decode("ascii"),
                key_id="",  # 调用方需自行填充
            )

        if suite == CipherSuite.DATABASE_DETERMINISTIC:
            # 确定性 nonce = HMAC(key, plaintext)[:12] — 相同明文总是产生相同 nonce
            if nonce is None:
                nonce = hmac.new(key, plaintext, hashlib.sha256).digest()[
                    :AES_NONCE_SIZE
                ]
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            ct = AESGCM(key).encrypt(nonce, plaintext, aad)
            return EncryptedPayload(
                encrypted=base64.b64encode(ct).decode("ascii"),
                nonce=base64.b64encode(nonce).decode("ascii"),
                key_id="",
            )

        raise ValueError(f"CryptoEngine.encrypt 不支持套件: {suite}（{suite.value}）")

    @staticmethod
    def decrypt(
        payload: EncryptedPayload,
        key: bytes,
        suite: CipherSuite,
        aad: bytes | None = None,
    ) -> bytes:
        """按套件解密。"""
        if suite in (CipherSuite.DATABASE_AES_GCM, CipherSuite.DATABASE_DETERMINISTIC):
            nonce = base64.b64decode(payload.nonce)
            ciphertext = base64.b64decode(payload.encrypted)
            return AesGcmEngine.decrypt(nonce, ciphertext, key, aad)

        raise ValueError(f"CryptoEngine.decrypt 不支持套件: {suite}（{suite.value}）")

    @staticmethod
    def blind_index(value: str, index_key: bytes, digest_size: int = 16) -> str:
        """
        生成盲索引 token。

        用于加密字段的等值查询：WHERE blind_index_col = CryptoEngine.blind_index(?)。
        相同 value + 相同 index_key → 相同 token。

        使用 HMAC-SHA256（不是裸哈希），防止彩虹表攻击。
        """
        token = hmac.new(
            index_key,
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[: digest_size * 2]  # digest_size 字节 → 2x 十六进制字符
        return token
