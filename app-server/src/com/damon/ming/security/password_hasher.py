"""用户密码专用哈希，不提供可逆加密能力。"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

_PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """生成带随机盐的 Argon2id 密码摘要。"""
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    """验证 Argon2id 摘要。"""
    try:
        return _PASSWORD_HASHER.verify(encoded_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
