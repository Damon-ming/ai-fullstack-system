# app-server/src/com/damon/ming/app/encryption/base_key_store.py
"""
密钥存储抽象接口 —— 业务层存储契约。

本文件从 encryption/key_store/ 迁移到 app/encryption/，
因为存储后端（内存 / DB）属于业务层关注点，不属于纯加密技术。

职责：
  - 定义 AES 会话密钥的持久化契约（key_id 维度）
  - 与具体存储后端解耦（内存 / PostgreSQL / SQLite / Redis 均可实现）

安全模型：
  - 存储的是"用 KEK 加密后的 AES 密钥"，不是明文
  - KEK 由上层通过环境变量注入，本模块不管理 KEK 生命周期
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredSession:
    """一条已持久化的 AES 会话密钥记录。as

    字段说明：
      key_id:        会话标识（明文，由业务层生成）
      aes_key_enc:   KEK 加密后的 AES-256 密钥（base64 编码）
      created_at:    创建时间
      expires_at:    过期时间
    """

    key_id: str
    aes_key_enc: str  # base64(KEK_encrypted_aes_key)
    created_at: datetime
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(tz=self.expires_at.tzinfo) > self.expires_at


# ---------------------------------------------------------------------------
# 抽象接口
# ---------------------------------------------------------------------------


class BaseKeyStore(ABC):
    """密钥存储后端抽象类（纯 key_id 索引，无业务维度）。

    业务扩展（如按 session_id 索引、按设备索引）由业务层存储实现自行管理。
    """

    @abstractmethod
    def initialize(self) -> None:
        """初始化存储后端（建表、建索引等）。"""
        ...

    @abstractmethod
    def save_session(self, session: StoredSession) -> None:
        """保存或更新一条会话记录。key_id 冲突时覆盖。"""
        ...

    @abstractmethod
    def get_session(self, key_id: str) -> StoredSession | None:
        """按 key_id 查找会话。已过期返回 None。"""
        ...

    @abstractmethod
    def remove_session(self, key_id: str) -> None:
        """删除指定会话。不存在时静默忽略。"""
        ...

    @abstractmethod
    def cleanup_expired(self) -> int:
        """清理所有过期会话。返回清理条数。"""
        ...

    @abstractmethod
    def count(self) -> int:
        """返回当前存储的会话总数（含未清理的过期条目）。"""
        ...
