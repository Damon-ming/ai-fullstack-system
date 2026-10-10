# app-server/src/com/damon/ming/encryption/key_store/__init__.py
"""
密钥存储后端 —— AES 会话密钥的持久化层（纯技术，可移植）。

提供：
  - BaseKeyStore:        存储后端抽象接口
  - StoredSession:       会话记录数据模型
  - MemoryKeyStore:      内存实现（开发 / fallback）
  - derive_kek / wrap_key / unwrap_key: KEK 派生与密钥加解密工具

DB 后端实现位于业务层 router/encryption/pg_key_store.py。

使用方式：
  # 纯内存（默认）
  store: BaseKeyStore = MemoryKeyStore()
  store.initialize()

  # 保存会话（AES 密钥先用 wrap_key 加密）
  store.save_session(StoredSession(
      key_id=session.key_id,
      aes_key_enc=wrap_key(session.aes_key, kek),
      device_id=device_id,
      created_at=...,
      expires_at=...,
  ))

  # 读取会话（AES 密钥用 unwrap_key 解密）
  record = store.get_session(key_id)
  aes_key = unwrap_key(record.aes_key_enc, kek)
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
