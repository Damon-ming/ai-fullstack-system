# app-server/src/com/damon/ming/encryption/key_management.py
"""
密钥管理服务

职责：
  - 启动时生成 RSA-2048 密钥对（公钥用于分发，私钥驻留内存）
  - 维护 AES 会话密钥表（客户端注册后分配的对称密钥）
  - 提供密钥过期清理

安全要点：
  - 私钥永不出内存，接口只暴露公钥 PEM
  - 会话 keyId 使用 secrets.token_urlsafe，不可预测
  - 会话有过期时间，过期后客户端需重新注册
"""

import secrets
import threading
import time
from dataclasses import dataclass, field

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class SessionKey:
    """一条已注册的 AES 会话密钥"""

    key_id: str
    aes_key: bytes  # 原始 AES-256 密钥（32 字节）
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)

    # 默认 24 小时过期；可根据业务调整
    ttl_seconds: int = 60 * 60 * 24

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds

    def touch(self) -> None:
        self.last_used_at = time.time()


# ---------------------------------------------------------------------------
# KeyManager
# ---------------------------------------------------------------------------


class KeyManager:
    """
    线程安全的密钥管理器。

    用法：
        km = KeyManager()
        km.initialize()  # 启动时调用一次

        # --- 公钥分发 ---
        pem = km.get_public_key_pem()

        # --- 会话注册（客户端用 RSA 公钥加密 AES 密钥后传来） ---
        session = km.register_session(encrypted_aes_key_bytes)

        # --- 解密时查找会话 ---
        session = km.get_session(session.key_id)
    """

    def __init__(self, rsa_key_size: int = 2048):
        self._rsa_key_size = rsa_key_size
        self._private_key: rsa.RSAPrivateKey | None = None
        self._public_key: rsa.RSAPublicKey | None = None
        self._public_key_pem: bytes | None = None

        # 会话表：key_id -> SessionKey
        self._sessions: dict[str, SessionKey] = {}
        self._lock = threading.RLock()

    # ---- 生命周期 -------------------------------------------------------

    def initialize(self) -> None:
        """生成 RSA 密钥对。应用启动时调用一次。"""
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self._rsa_key_size,
        )
        self._public_key = self._private_key.public_key()
        self._public_key_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    # ---- 公钥分发 -------------------------------------------------------

    def get_public_key_pem(self) -> bytes:
        """返回 RSA 公钥 PEM 格式（可安全分发给客户端）。"""
        if self._public_key_pem is None:
            raise RuntimeError("KeyManager not initialized. Call initialize() first.")
        return self._public_key_pem

    # ---- 会话注册 -------------------------------------------------------

    def register_session(self, encrypted_aes_key: bytes) -> SessionKey:
        """
        客户端使用 RSA 公钥加密 AES-256 密钥后，调用此方法注册会话。

        参数：
          encrypted_aes_key: 经 RSA-OAEP 加密的 32 字节 AES 密钥

        返回：
          SessionKey（含 key_id，客户端后续请求需带上）
        """
        # 1. RSA 解密拿到原始 AES 密钥
        aes_key = self._private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        if len(aes_key) not in (16, 24, 32):
            raise ValueError(f"Invalid AES key length: {len(aes_key)} bytes")

        # 2. 生成不可预测的 keyId
        key_id = secrets.token_urlsafe(24)  # ~32 字符

        session = SessionKey(key_id=key_id, aes_key=aes_key)
        with self._lock:
            self._cleanup_expired_unlocked()
            self._sessions[key_id] = session

        return session

    # ---- 会话查找 -------------------------------------------------------

    def get_session(self, key_id: str) -> SessionKey | None:
        """按 key_id 查找会话，同时做过期清理。找不到或已过期返回 None。"""
        with self._lock:
            session = self._sessions.get(key_id)
            if session is None:
                return None
            if session.is_expired:
                del self._sessions[key_id]
                return None
            session.touch()
            return session

    def remove_session(self, key_id: str) -> None:
        with self._lock:
            self._sessions.pop(key_id, None)

    # ---- 内部清理 -------------------------------------------------------

    def _cleanup_expired_unlocked(self) -> None:
        """调用者必须持有 _lock。"""
        expired = [k for k, v in self._sessions.items() if v.is_expired]
        for k in expired:
            del self._sessions[k]
