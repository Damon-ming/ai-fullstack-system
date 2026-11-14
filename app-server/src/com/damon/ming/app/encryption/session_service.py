# app-server/src/com/damon/ming/app/encryption/session_service.py
"""
加密会话服务 —— 业务层，协调 RSA 密钥对 + 存储后端 + KEK。

设计：DB 为唯一真源，无内存缓存。每次 get_session 直查 DB，
保证过期/删除/续签等状态变更即时生效。

职责：
  - 会话注册：RSA 解密 → 生成 keyId → 原子 DB 替换
  - 会话查找：直查 DB
  - 会话清理：DB cleanup_expired 处理

本模块是业务层对加密技术的"适配器"，上层（middleware / router）通过本模块
操作加密会话，不直接触碰 RSA / 存储后端内部。

依赖：
  - RSAKeyPair (encryption/v1/)         — RSA 解密
  - wrap_key / unwrap_key (encryption/key_store/) — KEK 加密工具
  - BaseKeyStore 实现 (同目录)          — 持久化后端
"""

from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from src.com.damon.ming.app.encryption.base_key_store import EncryptionSessionRecord
from src.com.damon.ming.app.encryption.key_management import DecryptedSessionKey
from src.com.damon.ming.app.encryption.key_store import PgKeyStore
from src.com.damon.ming.app.thread_pools import run_in_pool
from src.com.damon.ming.encryption.constants import AES_KEY_SIZES
from src.com.damon.ming.encryption.key_store import unwrap_key, wrap_key
from src.com.damon.ming.encryption.v1.rsa_key_pair import RSAKeyPair
from src.com.damon.ming.log import pin

logger = pin("app.encryption.session_service")


def _stored_ttl_seconds(stored: EncryptionSessionRecord) -> int:
    """从持久化记录还原会话有效期（秒）。

    写入时 expires_at - created_at 就是当轮的 ttl_seconds，
    因此读回时可直接反算，无需额外字段。
    """
    return int((stored.expires_at - stored.created_at).total_seconds())


class SessionService:
    """加密会话生命周期管理。

    组合 RSAKeyPair（纯技术）+ 存储后端（业务）+ KEK（配置注入），
    对外提供完整的加密会话管理。

    设计：DB 为唯一真源，无内存缓存。每次 get_session 直查 DB，
    保证 DB 的删除/过期/续签/失效等状态变更即时生效。

    用法：
        ss = SessionService(rsa_key_pair, kek, ttl_seconds, key_store=store)
        ss.initialize()                          # 清理 DB 中过期会话

        # 注册会话（原子替换）
        session = ss.register_and_replace(encrypted_aes_key, session_id)

        # 查找会话
        session = await ss.get_session(key_id, session_id)
    """

    def __init__(
        self,
        rsa_key_pair: RSAKeyPair,
        kek: bytes,
        ttl_seconds: int,
        *,
        key_store: PgKeyStore,
        db_executor: ThreadPoolExecutor,
    ) -> None:
        """
        参数：
          rsa_key_pair:  已初始化的 RSAKeyPair 实例。
          kek:         Key Encryption Key（业务配置派生）。
          ttl_seconds: 会话有效期（秒），从业务配置读取。
          key_store:   必填 DB 存储后端，不支持内存模式。
        """
        if key_store is None:
            raise RuntimeError("加密会话必须配置数据库密钥存储")
        if not kek:
            raise ValueError("加密会话 KEK 不能为空")
        self._rsa = rsa_key_pair
        self._kek = kek
        self._ttl_seconds = ttl_seconds
        self._key_store = key_store
        self._db_executor = db_executor

    def get_public_key_pem(self) -> bytes:
        """RSA 公钥 PEM（分发给客户端）。"""
        return self._rsa.get_public_key_pem()

    def initialize(self) -> None:
        """清理 DB 中过期会话。应用启动时调用一次。"""
        self._key_store.cleanup_expired()

    def register_and_replace(
        self, encrypted_aes_key: bytes, session_id: str
    ) -> DecryptedSessionKey:
        """注册新 AES 会话并原子替换该 session_id 旧记录。

        流程：
          1. RSA 解密 → 生成 keyId
          2. wrap_key → replace_session(session_id, new_stored)（原子 DELETE + INSERT）

        崩溃安全：
          - 步骤 1 崩溃 → 无影响（DB 无新记录）
          - 步骤 2 崩溃 → 事务 rollback，旧记录保留（客户端重试即可）

        参数：
          encrypted_aes_key: 经 RSA-OAEP 加密的 AES 密钥
          session_id:        业务会话标识

        返回：
          DecryptedSessionKey（含 key_id）
        """
        # 1. RSA 解密
        aes_key = self._rsa.decrypt(encrypted_aes_key)
        if len(aes_key) not in AES_KEY_SIZES:
            from src.com.damon.ming.exception import EncryptionError
            from src.com.damon.ming.exception.error_codes import ErrorCode

            raise EncryptionError(
                f"Invalid AES key length: {len(aes_key)} bytes",
                biz_code=ErrorCode.ENCRYPT.INVALID_KEY_FORMAT,
            )

        # 2. 生成 keyId
        key_id = secrets.token_urlsafe(24)
        session = DecryptedSessionKey(
            key_id=key_id,
            aes_key=aes_key,
            ttl_seconds=self._ttl_seconds,
        )

        # 3. 持久化（原子替换）
        expires_at = datetime.now(tz=UTC) + timedelta(seconds=session.ttl_seconds)
        stored = EncryptionSessionRecord(
            key_id=key_id,
            aes_key_enc=wrap_key(aes_key, self._kek),
            session_id=session_id,
            created_at=datetime.now(tz=UTC),
            expires_at=expires_at,
        )
        self._key_store.replace_session(session_id, stored)

        return session

    async def get_session(
        self, key_id: str, session_id: str | None = None
    ) -> DecryptedSessionKey | None:
        """查找会话（直查 DB，不走内存缓存）。

        DB 为唯一真源，保证过期/删除/续签等状态变更即时生效。

        Args:
            key_id:     加密会话标识
            session_id: 业务 session_id。非空时执行归属校验，
                        仅返回属于该 session_id 的密钥（防跨用户密钥泄露）。
        """
        # SECURITY: 拒绝空 session_id，防止绕过归属校验（P1-1 修复）
        if not session_id:
            logger.warning("加密会话查找拒绝: 空 session_id | key_id=%s", key_id[:12])
            return None

        # 直查 DB（卸载到线程池，不阻塞事件循环）
        stored = await run_in_pool(
            self._db_executor,
            self._key_store.get_session,
            key_id,
            session_id=session_id,
        )
        if stored is None:
            return None
        if not stored.session_id:
            logger.warning("加密会话归属信息缺失 | key_id=%s", key_id[:12])
            return None

        try:
            aes_key = unwrap_key(stored.aes_key_enc, self._kek)
        except Exception:
            return None

        return DecryptedSessionKey(
            key_id=stored.key_id,
            aes_key=aes_key,
            ttl_seconds=_stored_ttl_seconds(stored),
            created_at=stored.created_at.timestamp(),
        )
