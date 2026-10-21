# app-server/src/com/damon/ming/exception/error_codes.py
"""
统一错误码注册中心 — 分段式数字码

格式: A BB CCC DDD (9位)
  A    (第1位)    — 结果位: 1=成功, 2=失败, 3-9 预留
  BB   (第2-3位)  — 系统位: 00=当前服务(默认), 01-99=预留, 拆子系统时启用
  CCC  (第4-6位)  — 业务模块位: 000=通用, 001=参数校验, 002=加密, 003=认证...
  DDD  (第7-9位)  — 具体业务码: 同模块内递增

容量:
  结果:   9 个 (1-9)
  系统:   99 个 (01-99, 00=当前服务)
  业务:   999 个 (001-999, 000=通用)
  具体码: 999 个

示例:
  100000000 = 成功(通用)
  200002001 = 失败, 当前服务, 加密模块(002), AES密钥格式错误(001)
  200003001 = 失败, 当前服务, 认证模块(003), 缺少Token(001)
  200005001 = 失败, 当前服务, Chat模块(005), 请求超时(001)

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
# 系统位 (第2-3位) — 当前统一为 00, 拆子系统时启用
# ---------------------------------------------------------------------------


class System:
    """系统位 (第2-3位) — 物理/部署层面的子系统标识

    当前单体服务统一使用 GENERIC(00), 预留 01-99 等拆子系统时启用:
      01 = Chat 独立服务
      02 = Auth 独立服务
      03 = Account 独立服务
      ...
    """

    GENERIC = 0  # 00 当前服务(默认)


# ---------------------------------------------------------------------------
# 业务模块位 (CCC, 第4-6位) — 标识业务领域
# ---------------------------------------------------------------------------


class Business:
    """业务模块位 (第4-6位)"""

    GENERIC = 0  # 000 通用
    VALIDATION = 1  # 001 参数校验
    ENCRYPTION = 2  # 002 加密协议
    AUTH = 3  # 003 认证鉴权
    ACCOUNT = 4  # 004 账号体系
    CHAT = 5  # 005 AI/Chat
    UPLOAD = 6  # 006 文件上传
    SYSTEM = 7  # 007 系统/基础设施
    HISTORY = 8  # 008 对话历史


# ---------------------------------------------------------------------------
# 辅助函数 — 组装完整错误码
# ---------------------------------------------------------------------------


def _build(detail: int, business: int = 0, system: int = 0, result: int = 2) -> int:
    """组装错误码: result + BB + CCC + DDD"""
    return int(f"{result}{system:02d}{business:03d}{detail:03d}")


# ---------------------------------------------------------------------------
# 具体错误码 (完整9位)
# 格式: 2 00 CCC DDD
# ---------------------------------------------------------------------------


class _Success:
    """成功码"""

    OK = 100000000  # 通用成功


class _Validation:
    """参数校验错误 (2 00 001 xxx)"""

    PARAM_FORMAT = _build(detail=1, business=Business.VALIDATION)  # 200001001


class _Encryption:
    """加密协议错误 (2 00 002 xxx)"""

    INVALID_KEY_FORMAT = _build(detail=1, business=Business.ENCRYPTION)  # 200002001
    SESSION_REG_FAILED = _build(detail=2, business=Business.ENCRYPTION)  # 200002002
    UNSUPPORTED_VERSION = _build(detail=3, business=Business.ENCRYPTION)  # 200002003
    DECRYPTION_FAILED = _build(detail=4, business=Business.ENCRYPTION)  # 200002004
    META_DECRYPT_FAILED = _build(detail=5, business=Business.ENCRYPTION)  # 200002005
    SESSION_INVALID = _build(detail=6, business=Business.ENCRYPTION)  # 200002006
    SIGNATURE_FAILED = _build(detail=7, business=Business.ENCRYPTION)  # 200002007
    UNSUPPORTED_SIGNATURE_VERSION = _build(
        detail=8, business=Business.ENCRYPTION
    )  # 200002008
    SIGNATURE_REPLAY_DETECTED = _build(
        detail=9, business=Business.ENCRYPTION
    )  # 200002009


class _Auth:
    """认证鉴权错误 (2 00 003 xxx)"""

    MISSING_TOKEN = _build(detail=1, business=Business.AUTH)  # 200003001
    INVALID_TOKEN = _build(detail=2, business=Business.AUTH)  # 200003002
    MISSING_SESSION = _build(detail=3, business=Business.AUTH)  # 200003003
    INVALID_SESSION = _build(detail=4, business=Business.AUTH)  # 200003004
    SESSION_TOKEN_MISMATCH = _build(detail=5, business=Business.AUTH)  # 200003005


class _Account:
    """账号体系错误 (2 00 004 xxx)"""

    # 预留


class _Chat:
    """AI/Chat 错误 (2 00 005 xxx)"""

    TIMEOUT = _build(detail=1, business=Business.CHAT)  # 200005001
    UNKNOWN = _build(detail=2, business=Business.CHAT)  # 200005002
    GUARDRAIL_BLOCKED = _build(detail=3, business=Business.CHAT)  # 200005003


class _Upload:
    """文件上传错误 (2 00 006 xxx)"""

    UPLOAD_FAILED = _build(detail=1, business=Business.UPLOAD)  # 200006001
    IN_PROGRESS = _build(detail=2, business=Business.UPLOAD)  # 200006002
    OUT_OF_WINDOW = _build(detail=3, business=Business.UPLOAD)  # 200006003


class _History:
    """对话历史错误 (2 00 008 xxx)"""

    SAVE_FAILED = _build(detail=1, business=Business.HISTORY)  # 200008001
    NOT_FOUND = _build(detail=2, business=Business.HISTORY)  # 200008002
    DELETE_FAILED = _build(detail=3, business=Business.HISTORY)  # 200008003


class _System:
    """系统/基础设施错误 (2 00 007 xxx)

    注意: 这类错误描述的是某业务模块的底层设施故障,
          与具体业务模块的"协议级错误"区分开.
    """

    DATABASE_FAILURE = _build(detail=1, business=Business.SYSTEM)  # 200007001
    ENCRYPTION_FAILURE = _build(detail=2, business=Business.SYSTEM)  # 200007002
    UPLOAD_FAILURE = _build(detail=3, business=Business.SYSTEM)  # 200007003
    AI_FAILURE = _build(detail=4, business=Business.SYSTEM)  # 200007004
    AUTH_FAILURE = _build(detail=5, business=Business.SYSTEM)  # 200007005
    RATE_LIMITED = _build(detail=6, business=Business.SYSTEM)  # 200007006
    UNKNOWN = _build(detail=99, business=Business.SYSTEM)  # 200007099


# ---------------------------------------------------------------------------
# 统一命名空间 — 业务代码直接引用
# ---------------------------------------------------------------------------


class ErrorCode:
    """统一错误码命名空间"""

    # 成功
    OK = _Success.OK  # 100000000

    # 参数校验
    VALIDATION = _Validation

    # 加密协议
    ENCRYPT = _Encryption

    # 认证鉴权
    AUTH = _Auth

    # 账号体系
    ACCOUNT = _Account

    # AI/Chat
    CHAT = _Chat

    # 文件上传
    UPLOAD = _Upload

    # 对话历史
    HISTORY = _History

    # 系统/基础设施
    SYSTEM = _System


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _code_segments(code: int) -> tuple[str, str, str, str]:
    """将错误码拆分为四段字符串: (结果, 系统, 业务模块, 具体码)

    不足9位右补零, 保证老7位码也能兼容解析。
    """
    s = str(code).ljust(9, "0")
    return s[0], s[1:3], s[3:6], s[6:9]


def get_category(code: int) -> int:
    """获取结果位 (第1位)"""
    return int(_code_segments(code)[0])


def get_system(code: int) -> int:
    """获取系统位 (第2-3位, 2位数字)

    00=当前服务, 01-99=预留(等拆子系统时启用)
    """
    return int(_code_segments(code)[1])


def get_business(code: int) -> int:
    """获取业务模块位 (第4-6位, 3位数字)"""
    return int(_code_segments(code)[2])


def get_detail(code: int) -> int:
    """获取具体业务码 (第7-9位, 3位数字)"""
    return int(_code_segments(code)[3])


def is_success(code: int) -> bool:
    """判断是否成功码"""
    return get_category(code) == SUCCESS


def is_failure(code: int) -> bool:
    """判断是否失败码"""
    return get_category(code) == FAILURE


# 系统号 → 名称映射 (用于日志)
_SYSTEM_NAMES: dict[int, str] = {
    System.GENERIC: "current-service",
}


def get_system_name(code: int) -> str:
    """获取系统名称 (用于日志)"""
    system = get_system(code)
    return _SYSTEM_NAMES.get(system, f"unknown({system:02d})")


# 业务模块 → 名称映射 (用于日志)
_BUSINESS_NAMES: dict[int, str] = {
    Business.GENERIC: "generic",
    Business.VALIDATION: "validation",
    Business.ENCRYPTION: "encryption",
    Business.AUTH: "auth",
    Business.ACCOUNT: "account",
    Business.CHAT: "chat",
    Business.UPLOAD: "upload",
    Business.HISTORY: "history",
    Business.SYSTEM: "system-infra",
}


def get_business_name(code: int) -> str:
    """获取业务模块名称 (用于日志)"""
    business = get_business(code)
    return _BUSINESS_NAMES.get(business, f"unknown({business:03d})")


def format_code(code: int) -> str:
    """格式化错误码为可读字符串, 如 '200002001 -> FAILURE:current-service:encryption:001'"""
    category = (
        "SUCCESS"
        if is_success(code)
        else "FAILURE"
        if is_failure(code)
        else f"CAT{get_category(code)}"
    )
    system = get_system_name(code)
    business = get_business_name(code)
    detail = get_detail(code)
    return f"{code} -> {category}:{system}:{business}:{detail:03d}"
