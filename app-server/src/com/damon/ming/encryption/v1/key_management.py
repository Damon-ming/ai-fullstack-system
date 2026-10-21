# app-server/src/com/damon/ming/encryption/v1/key_management.py
"""
密钥材料管理 —— 纯技术层。

职责：
  - SessionKey 数据模型（AES 会话密钥）
  - 数据加密密钥版本轮换（用于数据库字段加解密）
  - 盲索引密钥管理

不包含 RSA 密钥对（已独立到 rsa_key_pair.py）。
不包含会话存储（已迁移到 app/encryption/session_service.py）。
"""

import secrets
import threading
import time
from dataclasses import dataclass, field

from src.com.damon.ming.encryption.v1.crypto_engine import AesGcmEngine
from src.com.damon.ming.exception import EncryptionError
from src.com.damon.ming.log import pin

logger = pin("encryption.key_management")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class SessionKey:
    """一条已注册的 AES 会话密钥（纯数据，无业务字段）。"""

    key_id: str
    aes_key: bytes  # 原始 AES-256 密钥（32 字节）
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    ttl_seconds: int  # 会话有效期（秒），由业务配置注入

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds

    def touch(self) -> None:
        self.last_used_at = time.time()


# ---------------------------------------------------------------------------
# 密钥材料管理器
# ---------------------------------------------------------------------------


class KeyMaterial:
    """数据加密密钥 + 盲索引密钥的管理器。

    数据密钥：用于数据库字段加解密，支持版本轮换（新写入用新版本，旧数据用旧密钥解密）。
    盲索引密钥：单一 key 即可，轮换需重建所有索引列。

    用法：
        km = KeyMaterial(data_key_id="data-key-v1")
        km.initialize()

        key = km.get_data_key()                # 获取当前活跃密钥
        km.rotate_data_key("data-key-v2")      # 轮换到新版本
        index_key = km.get_index_key()         # 获取盲索引密钥
    """

    def __init__(self, data_key_id: str = "") -> None:
        self._default_data_key_id = data_key_id
        self._data_keys: dict[str, bytes] = {}
        self._current_data_key_id: str = ""
        self._index_key: bytes = b""
        self._lock = threading.RLock()

    def initialize(self) -> None:
        """生成初始数据密钥和盲索引密钥。"""
        self._data_keys[self._default_data_key_id] = AesGcmEngine.generate_key()
        self._current_data_key_id = self._default_data_key_id
        self._index_key = secrets.token_bytes(32)

    def get_data_key(self, key_id: str = "") -> bytes:
        """获取数据加密密钥。

        参数：
          key_id: 密钥 ID。为空时返回当前活跃密钥（用于加密新数据）。
                 传入具体 ID 时返回历史密钥（用于解密旧数据）。
        """
        with self._lock:
            if not key_id:
                key_id = self._current_data_key_id
            key = self._data_keys.get(key_id)
            if key is None:
                from src.com.damon.ming.exception.error_codes import ErrorCode

                raise EncryptionError(
                    f"Data key not found: {key_id}",
                    biz_code=ErrorCode.ENCRYPT.SESSION_INVALID,
                )
            return key

    def rotate_data_key(self, new_key_id: str) -> None:
        """轮换数据密钥 — 生成新密钥并设为当前活跃密钥。

        旧密钥保留在 _data_keys 中（用于解密历史数据），
        新写入的数据使用新密钥。
        """
        with self._lock:
            if new_key_id in self._data_keys:
                raise ValueError(f"Data key already exists: {new_key_id}")
            self._data_keys[new_key_id] = AesGcmEngine.generate_key()
            self._current_data_key_id = new_key_id

    def get_index_key(self) -> bytes:
        """获取盲索引密钥。"""
        if not self._index_key:
            raise EncryptionError(
                "KeyMaterial not initialized. Call initialize() first."
            )
        return self._index_key
