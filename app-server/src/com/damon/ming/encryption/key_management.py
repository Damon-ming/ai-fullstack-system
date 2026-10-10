# app-server/src/com/damon/ming/encryption/key_management.py
"""
密钥管理服务

职责：
  - 启动时生成 RSA-2048 密钥对（公钥用于分发，私钥驻留内存）
  - 维护 AES 会话密钥表（客户端注册后分配的对称密钥）
  - 可选持久化到外部存储后端（PostgreSQL / 其他 BaseKeyStore 实现）
  - 提供密钥过期清理

用法：
  # 纯内存（向后兼容）
  km = KeyManager()
  km.initialize()

  # 持久化到 PostgreSQL（PgKeyStore 在业务层 router/encryption/）
  from src.com.damon.ming.router.encryption.pg_key_store import PgKeyStore
  from src.com.damon.ming.encryption.key_store import derive_kek
  store = PgKeyStore.from_connection_string("postgresql://user:pass@host/db")
  kek = derive_kek()  # 从 MASTER_KEY 环境变量派生
  km = KeyManager(key_store=store, kek=kek)
  km.initialize()

安全要点：
  - 私钥永不出内存，接口只暴露公钥 PEM
  - 会话 keyId 使用 secrets.token_urlsafe，不可预测
  - 会话有过期时间，过期后客户端需重新注册
  - 持久化时 AES 密钥经 KEK 加密后落盘，DB 泄露不暴露密钥
"""

import secrets
import threading
import time
from dataclasses import dataclass, field

from src.com.damon.ming.exception import EncryptionError
from datetime import UTC, datetime, timedelta

# BaseKeyStore 类型提示用（避免运行时导入，保持可选依赖）
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from src.com.damon.ming.encryption.crypto_engine import AesGcmEngine

if TYPE_CHECKING:
    from src.com.damon.ming.encryption.key_store.base_key_store import BaseKeyStore

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

    # 更新最后使用时间
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

    def __init__(
        self,
        rsa_key_size: int = 2048,
        key_store: "BaseKeyStore | None" = None,
        kek: bytes | None = None,
        session_ttl_seconds: int = 60 * 60 * 24,
    ):
        """
        参数：
          rsa_key_size: RSA 密钥位数
          key_store:    可选的持久化存储后端。
                        传入时，会话密钥会同步写入 store（AES 密钥经 KEK 加密后落盘）。
                        为 None 时保持纯内存行为（向后兼容）。
          kek:          Key Encryption Key，用于加密存储到 DB 的 AES 会话密钥。
                        当 key_store 不为 None 时必须提供。
          session_ttl_seconds: 会话密钥过期秒数（默认 24 小时）。
        """
        self._rsa_key_size = rsa_key_size
        self._session_ttl_seconds = session_ttl_seconds
        self._private_key: rsa.RSAPrivateKey | None = None
        self._public_key: rsa.RSAPublicKey | None = None
        self._public_key_pem: bytes | None = None

        # 持久化存储后端（可选）
        self._key_store = key_store
        self._kek = kek

        # 会话表：key_id -> SessionKey（内存缓存，加速读取）
        self._sessions: dict[str, SessionKey] = {}
        self._lock = threading.RLock()

        # 数据加密密钥：key_id -> AES-256 key（持久化，用于数据库字段加解密）
        # 与会话密钥分开管理 — 会话是 TTL 过期，数据密钥是版本轮换
        self._data_keys: dict[str, bytes] = {}
        self._current_data_key_id: str = ""

        # 盲索引密钥：单一 key 即可，轮换需重建所有索引列
        self._index_key: bytes = b""

    # ---- 生命周期 -------------------------------------------------------

    def initialize(self) -> None:
        """生成 RSA 密钥对和数据密钥，初始化存储后端。应用启动时调用一次。"""
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self._rsa_key_size,
        )
        self._public_key = self._private_key.public_key()
        # 把公钥导出成 **PEM 格式字节串**
        self._public_key_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # 初始化默认数据密钥
        default_key_id = "data-key-v1"
        self._data_keys[default_key_id] = AesGcmEngine.generate_key()
        self._current_data_key_id = default_key_id

        # 初始化盲索引密钥
        self._index_key = secrets.token_bytes(32)

        # 初始化持久化存储后端
        if self._key_store is not None:
            self._key_store.initialize()
            self._key_store.cleanup_expired()

    # ---- 公钥分发 -------------------------------------------------------

    def get_public_key_pem(self) -> bytes:
        """返回 RSA 公钥 PEM 格式（可安全分发给客户端）。"""
        if self._public_key_pem is None:
            raise EncryptionError("KeyManager not initialized. Call initialize() first.")
        return self._public_key_pem

    # ---- 会话注册 -------------------------------------------------------

    def register_session(
        self,
        encrypted_aes_key: bytes,
        device_id: str = "",
    ) -> SessionKey:
        """
        客户端使用 RSA 公钥加密 AES-256 密钥后，调用此方法注册会话。

        参数：
          encrypted_aes_key: 经 RSA-OAEP 加密的 32 字节 AES 密钥
          device_id:         客户端设备标识（可选，用于持久化时绑定用户）

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

        session = SessionKey(
            key_id=key_id, aes_key=aes_key, ttl_seconds=self._session_ttl_seconds
        )
        with self._lock:
            self._cleanup_expired_unlocked()
            self._sessions[key_id] = session

        # 3. 持久化到存储后端（如果配置了）
        if self._key_store is not None and self._kek is not None:
            from src.com.damon.ming.encryption.key_store import StoredSession, wrap_key

            expires_at = datetime.now(tz=UTC) + timedelta(seconds=session.ttl_seconds)
            stored = StoredSession(
                key_id=key_id,
                aes_key_enc=wrap_key(aes_key, self._kek),
                device_id=device_id,
                created_at=datetime.now(tz=UTC),
                expires_at=expires_at,
            )
            try:
                self._key_store.save_session(stored)
            except Exception:
                # 持久化失败不阻塞会话注册（降级为纯内存）
                import logging

                logging.getLogger("KeyManager").warning(
                    "会话持久化失败，降级为纯内存 | key_id=%s", key_id
                )

        return session

    # ---- 会话查找 -------------------------------------------------------

    def get_session(self, key_id: str) -> SessionKey | None:
        """按 key_id 查找会话。

        查找顺序：内存缓存 → 持久化存储 → None。
        从 store 加载成功后自动回填内存缓存。
        """
        with self._lock:
            session = self._sessions.get(key_id)
            if session is not None:
                if session.is_expired:
                    del self._sessions[key_id]
                    return None
                session.touch()
                return session

        # 内存 miss —— 尝试从 store 加载
        if self._key_store is not None and self._kek is not None:
            from src.com.damon.ming.encryption.key_store import (
                unwrap_key,
            )

            stored = self._key_store.get_session(key_id)
            if stored is not None:
                try:
                    aes_key = unwrap_key(stored.aes_key_enc, self._kek)
                except Exception:
                    return None
                session = SessionKey(
                    key_id=stored.key_id,
                    aes_key=aes_key,
                    created_at=stored.created_at.timestamp(),
                )
                with self._lock:
                    self._sessions[key_id] = session
                return session

        return None

    def remove_session(self, key_id: str) -> None:
        with self._lock:
            self._sessions.pop(key_id, None)
        if self._key_store is not None:
            self._key_store.remove_session(key_id)

    # ---- 内部清理 -------------------------------------------------------

    def _cleanup_expired_unlocked(self) -> None:
        """调用者必须持有 _lock。"""
        expired = [k for k, v in self._sessions.items() if v.is_expired]
        for k in expired:
            del self._sessions[k]

    # ---- 数据密钥（数据库字段加解密）------------------------------------

    def get_data_key(self, key_id: str = "") -> bytes:
        """
        获取数据加密密钥。

        参数：
          key_id: 密钥 ID。为空时返回当前活跃密钥（用于加密新数据）。
                 传入具体 ID 时返回历史密钥（用于解密旧数据）。
        """
        with self._lock:
            if not key_id:
                key_id = self._current_data_key_id
            key = self._data_keys.get(key_id)
            if key is None:
                raise KeyError(f"Data key not found: {key_id}")
            return key

    def rotate_data_key(self, new_key_id: str) -> None:
        """
        轮换数据密钥 — 生成新密钥并设为当前活跃密钥。

        旧密钥保留在 _data_keys 中（用于解密历史数据），
        新写入的数据使用新密钥。

        用法：
          km.rotate_data_key("data-key-v2")
          # 之后 encrypt() 默认用 v2，decrypt() 按密文中的 key_id 自动选
        """
        with self._lock:
            if new_key_id in self._data_keys:
                raise ValueError(f"Data key already exists: {new_key_id}")
            self._data_keys[new_key_id] = AesGcmEngine.generate_key()
            self._current_data_key_id = new_key_id

    # ---- 盲索引密钥 -----------------------------------------------------

    def get_index_key(self) -> bytes:
        """获取盲索引密钥。"""
        if not self._index_key:
            raise EncryptionError("KeyManager not initialized. Call initialize() first.")
        return self._index_key
