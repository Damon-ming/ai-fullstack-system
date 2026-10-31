# app-server/src/com/damon/ming/app/encryption/memory_key_store.py
"""
内存密钥存储 —— 业务层存储实现，不持久化。

适用场景：
  - 开发环境 / 单实例快速部署
  - 不需要跨重启保持会话
  - 作为无 DB 时的 fallback

本文件从 encryption/key_store/ 迁移到 app/encryption/。
"""

import threading

from src.com.damon.ming.app.encryption.base_key_store import (
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

    def get_session(
        self, key_id: str, session_id: str | None = None
    ) -> StoredSession | None:
        with self._lock:
            session = self._sessions.get(key_id)
            if session is None:
                return None
            if session.is_expired:
                del self._sessions[key_id]
                return None
            # SECURITY: 拒绝空 session_id，始终执行归属校验（P1-1 修复）
            if not session_id:
                return None
            if session.session_id and session.session_id != session_id:
                return None
            return session

    def remove_session(self, key_id: str) -> None:
        with self._lock:
            self._sessions.pop(key_id, None)

    def cleanup_expired(self) -> int:
        with self._lock:
            expired_keys = [k for k, v in self._sessions.items() if v.is_expired]
            for k in expired_keys:
                del self._sessions[k]
            return len(expired_keys)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
