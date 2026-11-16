"""生成需要保密的随机登录凭据。"""

import secrets


def generate_session_token() -> str:
    """生成含 32 字节随机熵的 URL 安全会话 token。"""
    return secrets.token_urlsafe(32)
