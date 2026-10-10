# app-server/src/com/damon/ming/exception/server_error.py
"""全局异常分类 —— 子系统错误码定义。

服务端记录完整堆栈，客户端只收到"哪类子系统出错"的提示，
不暴露内部实现细节（堆栈、SQL、密钥信息等）。
"""

from src.com.damon.ming.log import pin

logger = pin("app.error")


# ---------------------------------------------------------------------------
# 子系统专属异常基类 —— 用于全局异常处理器分类
# ---------------------------------------------------------------------------


class DatabaseError(Exception):
    """数据库子系统异常基类。"""


class EncryptionError(Exception):
    """加密子系统异常基类。"""


class ServerSubSystem:
    """子系统错误码（40100-40199）—— 用于指示错误来源分类。"""

    DATABASE = 40101  # 数据库操作失败
    ENCRYPTION = 40102  # 加密/解密失败
    UPLOAD = 40103  # 上传处理失败
    AI = 40104  # AI 推理失败
    AUTH = 40105  # 认证/鉴权失败
    UNKNOWN = 40199  # 未知子系统异常


# 异常类型 → 子系统码映射
_EXCEPTION_MAP: dict[type, int] = {}


def register_exception(exc_class: type, subsystem_code: int) -> None:
    """注册异常类型到子系统的映射。"""
    _EXCEPTION_MAP[exc_class] = subsystem_code


def classify_exception(exc: Exception) -> int:
    """根据异常类型判断属于哪个子系统。"""
    for exc_class, code in _EXCEPTION_MAP.items():
        if isinstance(exc, exc_class):
            return code
    return ServerSubSystem.UNKNOWN


def get_safe_message(subsystem_code: int) -> str:
    """返回给客户端的安全错误描述（不含内部细节）。"""
    _MESSAGES = {
        ServerSubSystem.DATABASE: "数据服务暂不可用，请稍后重试",
        ServerSubSystem.ENCRYPTION: "安全服务异常，请重新建立会话",
        ServerSubSystem.UPLOAD: "文件处理失败，请重试",
        ServerSubSystem.AI: "AI 服务暂不可用，请稍后重试",
        ServerSubSystem.AUTH: "认证失败，请重新登录",
        ServerSubSystem.UNKNOWN: "服务暂不可用，请稍后重试",
    }
    return _MESSAGES.get(subsystem_code, _MESSAGES[ServerSubSystem.UNKNOWN])
