"""异常处理基础设施 —— 子系统异常分类 + 全局异常处理器。"""

from src.com.damon.ming.exception.exception_handler import register_exception_handler
from src.com.damon.ming.exception.server_error import (
    DatabaseError,
    EncryptionError,
    ServerSubSystem,
    classify_exception,
    get_safe_message,
    register_exception,
)

__all__ = [
    "DatabaseError",
    "EncryptionError",
    "ServerSubSystem",
    "classify_exception",
    "get_safe_message",
    "register_exception",
    "register_exception_handler",
]
