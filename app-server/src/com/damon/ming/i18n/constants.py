# i18n/constants.py
"""
前端词条 key 注册表 —— 所有下发给前端的词条 key 集中管理。

命名规范：模块_场景_具体原因
前后端各自维护一份映射，通过 key 字符串解耦。
"""

from enum import StrEnum


class I18nKey(StrEnum):
    """所有下发给前端的词条 key。"""

    # ── 输入校验 ──
    VALIDATOR_EMPTY_INPUT = "validator.empty_input"
    VALIDATOR_INPUT_TOO_LONG = "validator.input_too_long"
    VALIDATOR_ILLEGAL_CHARS = "validator.illegal_chars"
    VALIDATOR_PROMPT_INJECTION = "validator.prompt_injection"
    VALIDATION_PARAM_FORMAT = "validation.param_format"

    # ── 护栏 ──
    GUARDRAIL_BLOCKED = "guardrail.blocked"

    # ── 限流 ──
    RATE_LIMITED = "rate_limited"

    # ── 聊天 / 推理 ──
    CHAT_TIMEOUT = "chat.timeout"
    CHAT_MODEL_ERROR = "chat.model_error"

    # ── 上传 ──
    UPLOAD_NO_EXTENSION = "upload.no_extension"
    UPLOAD_TYPE_REJECTED = "upload.type_rejected"
    UPLOAD_TOO_MANY_FILES = "upload.too_many_files"
    UPLOAD_SIZE_EXCEEDED = "upload.size_exceeded"
    UPLOAD_PARSE_FAILED = "upload.parse_failed"
    UPLOAD_VECTOR_DB_ERROR = "upload.vector_db_error"

    # ── 认证 ──
    AUTH_MISSING_SESSION = "auth.missing_session"
    AUTH_MISSING_TOKEN = "auth.missing_token"
    AUTH_INVALID_TOKEN = "auth.invalid_token"
    AUTH_INVALID_SESSION = "auth.invalid_session"
    AUTH_SESSION_MISMATCH = "auth.session_mismatch"

    # ── 历史 ──
    HISTORY_NOT_FOUND = "history.not_found"
    HISTORY_NO_PERMISSION = "history.no_permission"

    # ── 加密 ──
    ENCRYPT_UNSUPPORTED_VERSION = "encrypt.unsupported_version"
    ENCRYPT_DECRYPTION_FAILED = "encrypt.decryption_failed"
    ENCRYPT_SESSION_INVALID = "encrypt.session_invalid"
    ENCRYPT_SIGNATURE_FAILED = "encrypt.signature_failed"
    ENCRYPT_UNSUPPORTED_SIG_VERSION = "encrypt.unsupported_sig_version"
    ENCRYPT_INVALID_KEY_FORMAT = "encrypt.invalid_key_format"
    ENCRYPT_SESSION_REG_FAILED = "encrypt.session_reg_failed"
    ENCRYPT_REPLAY_DETECTED = "encrypt.replay_detected"

    # ── 子系统兜底 ──
    SYS_DATABASE_FAILURE = "sys.database_failure"
    SYS_ENCRYPTION_FAILURE = "sys.encryption_failure"
    SYS_UPLOAD_FAILURE = "sys.upload_failure"
    SYS_AI_FAILURE = "sys.ai_failure"
    SYS_AUTH_FAILURE = "sys.auth_failure"
    SYS_UNKNOWN_FAILURE = "sys.unknown_failure"

    # ── 通用 ──
    UNKNOWN_ERROR = "unknown_error"
