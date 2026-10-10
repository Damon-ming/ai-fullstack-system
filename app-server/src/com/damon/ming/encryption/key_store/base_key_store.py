# app-server/src/com/damon/ming/encryption/key_store/base_key_store.py
"""
密钥存储抽象接口 —— 纯技术定义，无业务逻辑。

职责：
  - 定义 AES 会话密钥的持久化契约
  - 与具体存储后端解耦（内存 / PostgreSQL / SQLite / Redis 均可实现）

安全模型：
  - 存储的是"用 KEK 加密后的 AES 密钥"，不是明文
  - KEK 由上层通过环境变量注入，本模块不管理 KEK 生命周期
  - 调用方负责将 SessionKey 序列化为存储格式，反之亦然

设计原则：
  - 纯 ABC + dataclass，零外部依赖
  - 不依赖 cryptography / psycopg2 / 任何 HTTP 框架
  - 可被独立移植到任何 Python 项目
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


# `frozen=True`：**把这个 dataclass 实例变成【不可变对象】，实例创建之后，不能修改它的属性**。
@dataclass(frozen=True)
class StoredSession:
    """一条已持久化的 AES 会话密钥记录。

    字段说明：
      key_id:        会话标识（明文，由 KeyManager 生成）
      aes_key_enc:   KEK 加密后的 AES-256 密钥（base64 编码）
      device_id:    绑定的设备/用户标识（可选，用于用户级密钥管理）
      created_at:    创建时间
      expires_at:    过期时间
    """

    key_id: str
    aes_key_enc: str  # base64(KEK_encrypted_aes_key)
    device_id: str
    created_at: datetime
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        # `tzinfo` 是读取这个 datetime 对象身上已经绑定好的时区实例，不是去 “获取 / 查询” 新时区。
        return datetime.now(tz=self.expires_at.tzinfo) > self.expires_at


# ---------------------------------------------------------------------------
# 抽象接口
# ---------------------------------------------------------------------------


class BaseKeyStore(ABC):
    """密钥存储后端抽象类。

    用法：
        store = MemoryKeyStore()
        store.initialize()

        store.save_session(session)
        record = store.get_session(key_id)
        store.remove_session(key_id)
        store.cleanup_expired()
    """

    @abstractmethod
    def initialize(self) -> None:
        """初始化存储后端（建表、建索引等）。应用启动时调用一次。"""
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
    def get_session_by_device(self, device_id: str) -> StoredSession | None:
        """按 device_id 查找活跃会话（每个设备最多一条）。"""
        ...

    @abstractmethod
    def remove_session(self, key_id: str) -> None:
        """删除指定会话。不存在时静默忽略。"""
        ...

    @abstractmethod
    def remove_by_device(self, device_id: str) -> None:
        """删除指定设备的所有会话。"""
        ...

    @abstractmethod
    def cleanup_expired(self) -> int:
        """清理所有过期会话。返回清理条数。"""
        ...

    @abstractmethod
    def count(self) -> int:
        """返回当前存储的会话总数（含未清理的过期条目）。"""
        ...
