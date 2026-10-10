# app-server/src/com/damon/ming/encryption/key_store/memory_key_store.py
"""
内存密钥存储 —— 纯内存实现，不持久化。

适用场景：
  - 开发环境 / 单实例快速部署
  - 不需要跨重启保持会话
  - 作为无 DB 依赖的 fallback

安全说明：
  - 重启后所有会话丢失，客户端需重新注册
  - 不绑定用户，纯 key_id 索引
"""

import threading

from src.com.damon.ming.encryption.key_store.base_key_store import (
    BaseKeyStore,
    StoredSession,
)


class MemoryKeyStore(BaseKeyStore):
    """线程安全的内存密钥存储。"""

    def __init__(self) -> None:
        self._sessions: dict[str, StoredSession] = {}
        self._lock = threading.RLock()

    def initialize(self) -> None:
        """内存存储无需初始化。"""

    def save_session(self, session: StoredSession) -> None:
        with self._lock:
            self._sessions[session.key_id] = session

    def get_session(self, key_id: str) -> StoredSession | None:
        with self._lock:
            session = self._sessions.get(key_id)
            if session is None:
                return None
            if session.is_expired:
                del self._sessions[key_id]
                return None
            return session

    def get_session_by_device(self, device_id: str) -> StoredSession | None:
        with self._lock:
            for session in self._sessions.values():
                if session.device_id == device_id and not session.is_expired:
                    return session
            return None

    def remove_session(self, key_id: str) -> None:
        with self._lock:
            self._sessions.pop(key_id, None)

    def remove_by_device(self, device_id: str) -> None:
        with self._lock:
            to_remove = [
                k for k, v in self._sessions.items() if v.device_id == device_id
            ]
            for k in to_remove:
                del self._sessions[k]

    def cleanup_expired(self) -> int:
        with self._lock:
            expired_keys = [k for k, v in self._sessions.items() if v.is_expired]
            for k in expired_keys:
                del self._sessions[k]
            return len(expired_keys)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
