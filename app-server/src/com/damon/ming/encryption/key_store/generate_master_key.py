# app-server/src/com/damon/ming/encryption/key_store/generate_master_key.py

import secrets

from src.com.damon.ming.encryption.constants import MASTER_KEY_MIN_LENGTH


def generate_master_key(length: int = MASTER_KEY_MIN_LENGTH) -> str:
    """生成安全的随机主密钥。

    默认长度取 MASTER_KEY_MIN_LENGTH（与启动前校验的下限一致），
    保证生成出来的密钥一定能通过校验。
    """
    return secrets.token_urlsafe(length)
