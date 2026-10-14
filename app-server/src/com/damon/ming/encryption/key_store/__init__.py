# app-server/src/com/damon/ming/encryption/key_store/__init__.py
"""
密钥存储后端 —— AES 会话密钥的持久化层（纯技术，可移植）。

提供：
  - BaseKeyStore:        存储后端抽象接口（纯 key_id 索引）
  - StoredSession:       会话记录数据模型（无业务字段）
  - MemoryKeyStore:      内存实现（开发 / fallback）
  - derive_kek / wrap_key / unwrap_key: KEK 派生与密钥加解密工具

业务扩展（如按设备索引）由业务层存储实现（router/encryption/）自行管理。

DB 后端实现位于业务层 router/encryption/key_store.py。
"""

from src.com.damon.ming.encryption.key_store.base_key_store import (
    BaseKeyStore,
    StoredSession,
)
from src.com.damon.ming.encryption.key_store.kek_provider import (
    derive_kek,
    unwrap_key,
    wrap_key,
)
from src.com.damon.ming.encryption.key_store.memory_key_store import MemoryKeyStore

__all__ = [
    "BaseKeyStore",
    "MemoryKeyStore",
    "StoredSession",
    "derive_kek",
    "unwrap_key",
    "wrap_key",
]
