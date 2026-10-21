# app-server/src/com/damon/ming/encryption/v1/rsa_key_pair.py
"""
RSA 密钥对 —— 纯技术，可移植。

职责：
  - 启动时生成 RSA-2048 密钥对
  - 公钥分发（PEM 格式）
  - 私钥解密（RSA-OAEP）

私钥永不出内存。
"""

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from src.com.damon.ming.exception import EncryptionError


class RSAKeyPair:
    """RSA 密钥对容器。

    用法：
        kp = RSAKeyPair(key_size=2048)
        kp.initialize()  # 生成密钥对

        pem = kp.get_public_key_pem()           # 分发给客户端
        plaintext = kp.decrypt(ciphertext)      # 客户端用公钥加密后传来
    """

    def __init__(self, key_size: int = 2048) -> None:
        self._key_size = key_size
        self._private_key: rsa.RSAPrivateKey | None = None
        self._public_key: rsa.RSAPublicKey | None = None
        self._public_key_pem: bytes | None = None

    def initialize(self) -> None:
        """生成 RSA 密钥对。应用启动时调用一次。"""
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self._key_size,
        )
        self._public_key = self._private_key.public_key()
        self._public_key_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def get_public_key_pem(self) -> bytes:
        """返回 RSA 公钥 PEM 格式（可安全分发给客户端）。"""
        if self._public_key_pem is None:
            raise EncryptionError(
                "RSAKeyPair not initialized. Call initialize() first."
            )
        return self._public_key_pem

    def decrypt(self, ciphertext: bytes) -> bytes:
        """RSA-OAEP 解密。客户端用公钥加密后传来，服务端用私钥解密。"""
        if self._private_key is None:
            raise EncryptionError(
                "RSAKeyPair not initialized. Call initialize() first."
            )
        return self._private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
