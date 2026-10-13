# app-server/src/com/damon/ming/exception/error_codes.py
"""
统一错误码注册中心 — 分段式数字码

格式: A BBB CCC [DD...] (7位起，无上限)
  A    (第1位)    — 结果位: 1=成功, 2=失败, 3-9 预留
  BBB  (第2-4位)  — 系统位: 000=通用, 001-999=具体子系统
  CCC  (第5-7位)  — 业务位: 000=通用, 001-999=具体业务
  DD... (第8位起) — 具体业务码: 无位数限制

容量:
  结果: 9 个 (1-9)
  系统: 999 个 (001-999, 000=通用)
  业务: 999 个 (001-999, 000=通用)
  具体码: 无上限

示例:
  1000000 = 成功(通用)
  2001001 = 失败, 加密协议(001), 密钥格式错误(001)
  2002001 = 失败, 认证鉴权(002), 缺少Token(001)
  2006001 = 失败, 数据库(006), 数据库故障(001)
  1001001999999 = 成功, 加密协议(001), 密钥格式错误(001), 具体码(999999)

使用方式:
  from src.com.damon.ming.exception.error_codes import ErrorCode
  return BaseFailedResponse(code=ErrorCode.ENCRYPT.INVALID_KEY_FORMAT, ...)
"""

# ---------------------------------------------------------------------------
# 结果位 (第1位)
# ---------------------------------------------------------------------------

SUCCESS = 1
FAILURE = 2


# ---------------------------------------------------------------------------
# 系统位 (第2-4位) — 每个系统占一段
# ---------------------------------------------------------------------------


class System:
    """系统号 (第2-4位)"""

    GENERIC = 0  # 000 通用
    ENCRYPTION = 1  # 001 加密协议
    AUTH = 2  # 002 认证鉴权
    ACCOUNT = 3  # 003 账号体系
    CHAT = 4  # 004 AI/Chat
    UPLOAD = 5  # 005 文件上传
    # 006-099 预留系统
    DATABASE = 6  # 006 数据库/基础设施


# ---------------------------------------------------------------------------
# 具体错误码 (完整7位起)
# ---------------------------------------------------------------------------


class _Success:
    """成功码"""

    OK = 1000000  # 通用成功


class _Encryption:
    """加密协议错误 (2 001 xxx)"""

    INVALID_KEY_FORMAT = 2001001  # AES 密钥格式错误
    SESSION_REG_FAILED = 2001002  # 会话注册失败
    UNSUPPORTED_VERSION = 2001003  # 不支持的加密版本
    DECRYPTION_FAILED = 2001004  # JSON 解密失败
    META_DECRYPT_FAILED = 2001005  # Meta 解密失败
    SESSION_INVALID = 2001006  # 会话无效/过期
    SIGNATURE_FAILED = 2001007  # 签名验证失败
    UNSUPPORTED_SIGNATURE_VERSION = 2001008  # 不支持的签名协议版本


class _Auth:
    """认证鉴权错误 (2 002 xxx)"""

    MISSING_TOKEN = 2002001  # 缺少认证 Token
    INVALID_TOKEN = 2002002  # Token 无效/过期
    MISSING_SESSION = 2002003  # 缺少会话 ID
    INVALID_SESSION = 2002004  # 会话无效/过期
    SESSION_TOKEN_MISMATCH = 2002005  # 会话不属于该 Token


class _Chat:
    """AI/Chat 错误 (2 004 xxx)"""

    TIMEOUT = 2004001  # 请求超时
    UNKNOWN = 2004002  # 未知异常


class _Upload:
    """文件上传错误 (2 005 xxx)"""

    UPLOAD_FAILED = 2005001  # 上传失败
    IN_PROGRESS = 2005002  # 资料库正在更新中


class _System:
    """系统/基础设施错误 (2 006 xxx)"""

    DATABASE_FAILURE = 2006001  # 数据库故障
    ENCRYPTION_FAILURE = 2006002  # 加密子系统故障
    UPLOAD_FAILURE = 2006003  # 上传子系统故障
    AI_FAILURE = 2006004  # AI 子系统故障
    AUTH_FAILURE = 2006005  # 认证子系统故障
    UNKNOWN = 200699  # 未知系统故障


class _Validation:
    """参数校验错误 (2 000 xxx)"""

    PARAM_FORMAT = 2000001  # 请求参数格式错误


# ---------------------------------------------------------------------------
# 兼容旧名（过渡期保留）
# ---------------------------------------------------------------------------

Module = System


# ---------------------------------------------------------------------------
# 统一命名空间 — 业务代码直接引用
# ---------------------------------------------------------------------------


class ErrorCode:
    """统一错误码命名空间"""

    # 成功
    OK = _Success.OK  # 1000000

    # 加密协议
    ENCRYPT = _Encryption

    # 认证鉴权
    AUTH = _Auth

    # AI/Chat
    CHAT = _Chat

    # 文件上传
    UPLOAD = _Upload

    # 系统/基础设施
    SYSTEM = _System

    # 参数校验
    VALIDATION = _Validation


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _code_segments(code: int) -> tuple[str, str, str, str]:
    """将错误码拆分为四段字符串: (结果, 系统, 业务, 具体码)"""
    s = str(code).ljust(7, "0")  # 不足7位右补零
    return s[0], s[1:4], s[4:7], s[7:]


def get_category(code: int) -> int:
    """获取结果位 (第1位)"""
    return int(_code_segments(code)[0])


def get_system(code: int) -> int:
    """获取系统位 (第2-4位, 3位数字)"""
    return int(_code_segments(code)[1])


def get_business(code: int) -> int:
    """获取业务位 (第5-7位, 3位数字)"""
    return int(_code_segments(code)[2])


def get_detail(code: int) -> int:
    """获取具体业务码 (第8位起)，7位码返回 0"""
    detail_str = _code_segments(code)[3]
    return int(detail_str) if detail_str else 0


def is_success(code: int) -> bool:
    """判断是否成功码"""
    return get_category(code) == SUCCESS


def is_failure(code: int) -> bool:
    """判断是否失败码"""
    return get_category(code) == FAILURE


# 兼容旧名（过渡期保留）
get_module = get_system


# 系统号 → 名称映射 (用于日志)
_SYSTEM_NAMES: dict[int, str] = {
    System.GENERIC: "generic",
    System.ENCRYPTION: "encryption",
    System.AUTH: "auth",
    System.ACCOUNT: "account",
    System.CHAT: "chat",
    System.UPLOAD: "upload",
    System.DATABASE: "database",
}


def get_system_name(code: int) -> str:
    """获取系统名称 (用于日志)"""
    system = get_system(code)
    return _SYSTEM_NAMES.get(system, f"unknown({system:03d})")


# 兼容旧名（过渡期保留）
get_module_name = get_system_name


def format_code(code: int) -> str:
    """格式化错误码为可读字符串，如 '2001001 -> FAILURE:encryption:001'"""
    category = (
        "SUCCESS"
        if is_success(code)
        else "FAILURE"
        if is_failure(code)
        else f"CAT{get_category(code)}"
    )
    system = get_system_name(code)
    business = get_business(code)
    detail = get_detail(code)
    result = f"{code} -> {category}:{system}:{business:03d}"
    if detail > 0:
        result += f":{detail}"
    return result
