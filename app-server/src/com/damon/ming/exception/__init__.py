"""异常处理基础设施 —— 统一错误码 + 子系统异常分类 + 全局异常处理器。"""

from src.com.damon.ming.exception.error_codes import (
    FAILURE,
    SUCCESS,
    Business,
    ErrorCode,
    System,
    format_code,
    get_business,
    get_business_name,
    get_category,
    get_detail,
    get_system,
    get_system_name,
    is_failure,
    is_success,
)
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
    "FAILURE",
    "SUCCESS",
    "Business",
    "DatabaseError",
    "EncryptionError",
    "ErrorCode",
    "ServerSubSystem",
    "System",
    "classify_exception",
    "format_code",
    "get_business",
    "get_business_name",
    "get_category",
    "get_detail",
    "get_safe_message",
    "get_system",
    "get_system_name",
    "is_failure",
    "is_success",
    "register_exception",
    "register_exception_handler",
]
