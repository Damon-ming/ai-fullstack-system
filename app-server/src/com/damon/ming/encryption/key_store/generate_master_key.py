# app-server/src/com/damon/ming/encryption/generate_master_key.py

import secrets


def generate_master_key(length: int = 36) -> str:
    """生成安全的随机主密钥。"""
    return secrets.token_urlsafe(length)
