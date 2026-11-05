# app-server/src/com/damon/ming/router/account/service/account_service.py
"""
账号体系 业务逻辑层 —— 跨模块调用入口。

只暴露其他模块真正需要的最小访问单元，不把 users / devices / sessions
的表结构与行对象（UserRow / DeviceRow / SessionRow）交给调用方：
  - is_token_valid(token)        token 是否有效（滚动 TTL + 绝对 TTL）
  - get_session_info(session_id) 会话归属 token + 签发时 UA 指纹
  - get_phone_by_token(token)    token → 手机号
  - get_file_uploader_map()      文件路径 → 上传者昵称

account_router 自己仍直接使用 token_store（模块内访问不走本层）。
"""

from dataclasses import dataclass

from src.com.damon.ming.log import pin
from src.com.damon.ming.router.account import token_store

logger = pin("account.service")


@dataclass(frozen=True)
class SessionInfo:
    """会话投影 —— 跨模块只暴露这两个字段。

    SessionRow 还有 session_id / device_id / created_at / expires_at，
    调用方不需要，就不给。
    """

    token: str
    ua_hash: str = ""


class AccountService:
    """账号体系业务逻辑（供 account 以外的模块调用）。"""

    @staticmethod
    def is_token_valid(token: str) -> bool:
        """token 是否存在且未过期。"""
        return token_store.is_token_valid(token)

    @staticmethod
    def get_session_info(session_id: str) -> SessionInfo | None:
        """查询有效会话的归属 token 与签发时 UA 指纹。

        会话不存在或已过期时返回 None。
        """
        session = token_store.get_session(session_id)
        if session is None:
            return None
        return SessionInfo(token=session.token, ua_hash=session.issued_ua_hash)

    @staticmethod
    def get_phone_by_token(token: str) -> str | None:
        """token → 手机号。"""
        return token_store.get_phone_by_token(token)

    @staticmethod
    def get_file_uploader_map() -> dict[str, str]:
        """文件路径 → 上传者昵称（知识库展示用）。"""
        return token_store.get_file_uploader_map()
