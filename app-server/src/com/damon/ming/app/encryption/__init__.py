# app-server/src/com/damon/ming/app/encryption/__init__.py
"""
加密业务层 —— 存储后端实现 + 会话生命周期管理。

本目录属于业务层，集中了所有加密相关的业务组件：
  - base_key_store.py:    存储后端抽象接口 + EncryptionSessionRecord
  - key_store.py:         PgKeyStore（PostgreSQL 存储实现）
  - session_key.py:       DecryptedSessionKey 客户端会话密钥数据
  - field_key_material.py: KeyMaterial 字段加密和盲索引密钥材料
  - session_service.py:   会话生命周期管理（强制 DB 持久化，无密钥缓存）

纯加密技术（RSA、AES、签名）在 encryption/ 目录，本目录不重复。
"""

from src.com.damon.ming.app.encryption.base_key_store import (
    BaseKeyStore,
    EncryptionSessionRecord,
)
from src.com.damon.ming.app.encryption.field_key_material import KeyMaterial
from src.com.damon.ming.app.encryption.session_key import DecryptedSessionKey
from src.com.damon.ming.app.encryption.session_service import SessionService

__all__ = [
    "BaseKeyStore",
    "DecryptedSessionKey",
    "EncryptionSessionRecord",
    "KeyMaterial",
    "SessionService",
]
