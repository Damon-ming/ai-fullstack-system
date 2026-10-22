# app-server/src/com/damon/ming/app/encryption/session_service.py
"""
加密会话服务 —— 业务层，协调 RSA 密钥对 + 存储后端 + KEK。

职责：
  - 会话注册：RSA 解密 → 生成 keyId → 内存表 + 原子 DB 替换
  - 会话查找：内存优先，DB 兜底
  - 会话清理：按 session_id 清除所有记录

本模块是业务层对加密技术的"适配器"，上层（middleware / router）通过本模块
操作加密会话，不直接触碰 RSA / 存储后端内部。

依赖：
  - RSAKeyPair (encryption/v1/)         — RSA 解密
  - wrap_key / unwrap_key (encryption/key_store/) — KEK 加密工具
  - BaseKeyStore 实现 (同目录)          — 持久化后端
"""

import asyncio
import secrets
import threading
from datetime import UTC, datetime, timedelta

from src.com.damon.ming.app.encryption.base_key_store import StoredSession
from src.com.damon.ming.encryption.key_store import unwrap_key, wrap_key
from src.com.damon.ming.encryption.v1.key_management import SessionKey
from src.com.damon.ming.encryption.v1.rsa_key_pair import RSAKeyPair
from src.com.damon.ming.log import pin

logger = pin("app.encryption.session_service")


class SessionService:
    """加密会话生命周期管理。

    组合 RSAKeyPair（纯技术）+ 存储后端（业务）+ KEK（配置注入），
    对外提供完整的加密会话管理。

    用法：
        ss = SessionService(rsa_key_pair, kek)
        ss.initialize()                          # 初始化存储后端
        ss.set_key_store(store)                  # 设置存储后端（有 DB 时）

        # 注册会话（原子替换）
        session = ss.register_and_replace(encrypted_aes_key, session_id)

        # 查找会话
        session = ss.get_session(key_id)

        # 清理会话
        ss.clear_session(session_id)
    """

    def __init__(self, rsa_key_pair: RSAKeyPair, kek: bytes, ttl_seconds: int) -> None:
        """
        参数：
          rsa_key_pair:  已初始化的 RSAKeyPair 实例。
          kek:         Key Encryption Key（业务配置派生）。
          ttl_seconds: 会话有效期（秒），从业务配置读取。
        """
        self._rsa = rsa_key_pair
        self._kek = kek
        self._ttl_seconds = ttl_seconds
        self._key_store = None  # 可选存储后端
        self._sessions: dict[str, SessionKey] = {}
        # 内存归属索引：key_id → session_id（业务层 session，用于所有权校验）
        self._key_to_session: dict[str, str] = {}
        self._lock = threading.RLock()

    @property
    def rsa_key_pair(self) -> RSAKeyPair:
        """底层 RSA 密钥对（公钥分发仍直接操作）。"""
        return self._rsa

    def set_key_store(self, store) -> None:
        """设置持久化存储后端（有 DB 时调用）。"""
        self._key_store = store

    def initialize(self) -> None:
        """初始化存储后端。应用启动时调用一次。"""
        if self._key_store is not None:
            self._key_store.initialize()
            self._key_store.cleanup_expired()

    def register_and_replace(
        self, encrypted_aes_key: bytes, session_id: str
    ) -> SessionKey:
        """注册新 AES 会话并原子替换该 session_id 旧记录。

        流程：
          1. RSA 解密 → 生成 keyId → 内存表写入
          2. wrap_key → replace_session(session_id, new_stored)（原子 DELETE + INSERT）

        崩溃安全：
          - 步骤 1 崩溃 → 无影响（内存 + DB 均无新记录）
          - 步骤 2 崩溃 → 事务 rollback，旧记录保留（客户端重试即可）

        参数：
          encrypted_aes_key: 经 RSA-OAEP 加密的 AES 密钥
          session_id:        业务会话标识

        返回：
          SessionKey（含 key_id）
        """
        # 1. RSA 解密
        aes_key = self._rsa.decrypt(encrypted_aes_key)
        if len(aes_key) not in (16, 24, 32):
            from src.com.damon.ming.exception import EncryptionError
            from src.com.damon.ming.exception.error_codes import ErrorCode

            raise EncryptionError(
                f"Invalid AES key length: {len(aes_key)} bytes",
                biz_code=ErrorCode.ENCRYPT.INVALID_KEY_FORMAT,
            )

        # 2. 生成 keyId + 内存写入
        key_id = secrets.token_urlsafe(24)
        session = SessionKey(
            key_id=key_id,
            aes_key=aes_key,
            ttl_seconds=self._ttl_seconds,
        )
        with self._lock:
            self._cleanup_expired_unlocked()
            # 清理同一 session_id 的旧 key_id（防映射表膨胀 + 确保归属唯一）
            # 先保存旧 session 引用，DB 失败时可回滚恢复
            old_keys = [k for k, s in self._key_to_session.items() if s == session_id]
            old_sessions = {k: self._sessions.pop(k, None) for k in old_keys}
            for old_key in old_keys:
                self._key_to_session.pop(old_key, None)
            self._sessions[key_id] = session
            self._key_to_session[key_id] = session_id

            # 3. 持久化（锁内操作，失败时回滚内存）
            if self._key_store is not None:
                expires_at = datetime.now(tz=UTC) + timedelta(
                    seconds=session.ttl_seconds
                )
                stored = StoredSession(
                    key_id=key_id,
                    aes_key_enc=wrap_key(aes_key, self._kek),
                    session_id=session_id,
                    created_at=datetime.now(tz=UTC),
                    expires_at=expires_at,
                )
                try:
                    self._key_store.replace_session(session_id, stored)
                except Exception as e:
                    # DB 失败 → 回滚内存：移除新 key，恢复旧 key
                    self._sessions.pop(key_id, None)
                    self._key_to_session.pop(key_id, None)
                    for old_key, old_session in old_sessions.items():
                        if old_session is not None:
                            self._sessions[old_key] = old_session
                            self._key_to_session[old_key] = session_id
                    logger.error(
                        "会话持久化失败，已回滚内存 | key_id=%s session_id=%s error=%s",
                        key_id[:12],
                        session_id[:8],
                        e,
                    )
                    raise

        return session

    def get_session(
        self, key_id: str, session_id: str | None = None
    ) -> SessionKey | None:
        """查找会话。内存优先，miss 时从 DB 加载并回填。

        Args:
            key_id:     加密会话标识
            session_id: 业务 session_id。非空时执行归属校验，
                        仅返回属于该 session_id 的密钥（防跨用户密钥泄露）。
        """
        # 1. 内存查找
        with self._lock:
            session = self._sessions.get(key_id)
            if session is not None:
                if session.is_expired:
                    del self._sessions[key_id]
                    self._key_to_session.pop(key_id, None)
                    return None
                # 归属校验：调用者传了 session_id 时，检查内存映射
                if session_id:
                    owner = self._key_to_session.get(key_id)
                    if owner and owner != session_id:
                        logger.warning(
                            "加密会话归属不匹配 | key_id=%s owner=%s requester=%s",
                            key_id[:12],
                            owner[:8],
                            session_id[:8],
                        )
                        return None
                session.touch()
                return session

        # 2. DB 查找（session_id 透传给 store 层执行过滤）
        if self._key_store is None:
            return None

        stored = self._key_store.get_session(key_id, session_id=session_id)
        if stored is None:
            return None

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
            # 回填 DB 中的归属关系到内存映射
            if stored.session_id:
                self._key_to_session[key_id] = stored.session_id

        return session

    async def get_session_async(
        self, key_id: str, session_id: str | None = None
    ) -> SessionKey | None:
        """异步查找会话（缓存 miss 时通过线程池查 DB，不阻塞事件循环）。

        供 async 中间件/路由调用，替代同步 get_session()。

        Args:
            key_id:     加密会话标识
            session_id: 业务 session_id。非空时执行归属校验，
                        仅返回属于该 session_id 的密钥（防跨用户密钥泄露）。
        """
        # 1. 内存查找（同步，极快，锁内仅 dict 操作）
        with self._lock:
            session = self._sessions.get(key_id)
            if session is not None:
                if session.is_expired:
                    del self._sessions[key_id]
                    self._key_to_session.pop(key_id, None)
                    return None
                if session_id:
                    owner = self._key_to_session.get(key_id)
                    if owner and owner != session_id:
                        logger.warning(
                            "加密会话归属不匹配 | key_id=%s owner=%s requester=%s",
                            key_id[:12],
                            owner[:8],
                            session_id[:8],
                        )
                        return None
                session.touch()
                return session

        # 2. 内存 miss → DB 查找卸载到线程池（不阻塞事件循环）
        if self._key_store is None:
            return None

        loop = asyncio.get_running_loop()

        def _db_lookup() -> StoredSession | None:
            return self._key_store.get_session(key_id, session_id=session_id)

        stored = await loop.run_in_executor(None, _db_lookup)
        if stored is None:
            return None

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
            if stored.session_id:
                self._key_to_session[key_id] = stored.session_id
        return session

    def clear_session(self, session_id: str) -> None:
        """清除某 session_id 关联的所有加密记录（内存 + DB）。"""
        with self._lock:
            keys = [k for k, s in self._key_to_session.items() if s == session_id]
            for k in keys:
                self._sessions.pop(k, None)
                self._key_to_session.pop(k, None)
        if self._key_store is not None:
            self._key_store.replace_session(session_id, None)

    def remove_session(self, key_id: str) -> None:
        """删除指定会话（内存 + DB）。"""
        with self._lock:
            self._sessions.pop(key_id, None)
            self._key_to_session.pop(key_id, None)
        if self._key_store is not None:
            self._key_store.remove_session(key_id)

    # ---- 内部清理 -------------------------------------------------------

    def _cleanup_expired_unlocked(self) -> None:
        """调用者必须持有 _lock。"""
        expired = [k for k, v in self._sessions.items() if v.is_expired]
        for k in expired:
            del self._sessions[k]
            self._key_to_session.pop(k, None)
