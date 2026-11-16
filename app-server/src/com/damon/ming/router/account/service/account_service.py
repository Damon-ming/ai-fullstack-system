# app-server/src/com/damon/ming/router/account/service/account_service.py
"""
账号体系 业务逻辑层 —— 跨模块调用入口。

只暴露其他模块真正需要的最小访问单元，不把 users / devices / sessions
的表结构与行对象交给调用方：
  - authenticate_token(token, device_id) 校验并续期设备会话
  - get_phone_by_user_id(user_id) 内部用户 ID → 手机号

account_router 自己仍直接使用 token_store（模块内访问不走本层）。
"""

from src.com.damon.ming.log import pin
from src.com.damon.ming.router.account import token_store

logger = pin("account.service")


class AccountService:
    """账号体系业务逻辑（供 account 以外的模块调用）。"""

    @staticmethod
    def authenticate_token(token: str, device_id: str) -> tuple[int, str] | None:
        return token_store.authenticate_token(token, device_id)

    @staticmethod
    def get_phone_by_user_id(user_id: int) -> str | None:
        """user_id → 手机号。"""
        return token_store.get_phone_by_user_id(user_id)
