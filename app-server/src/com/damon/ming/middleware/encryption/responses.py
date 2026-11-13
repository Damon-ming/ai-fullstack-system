# app-server/src/com/damon/ming/middleware/encryption/responses.py
"""拒绝响应工厂 + 协议版本校验。

所有 4xx 响应集中在这里：gate 只表达「拒绝了」，不重复拼响应体。
错误码与 i18n key 的对应关系见 exception/error_codes.py 与
i18n/constants.py（ENCRYPT 段 = 200002xxx）。
"""

from src.com.damon.ming.encryption.constants import (
    SUPPORTED_ENCRYPTION_VERSIONS,
    SUPPORTED_SIGNATURE_VERSIONS,
)
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.schemas.response import BaseBizFailedData, BaseFailedResponse
from starlette.responses import JSONResponse


def _failed(status_code: int, code: int, i18n_key: str, **i18n_params) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=BaseFailedResponse(
            code=code,
            data=BaseBizFailedData(error_msg=t(i18n_key, **i18n_params)),
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# 响应工厂
# ---------------------------------------------------------------------------


def encryption_required_response() -> JSONResponse:
    """「当前环境要求加密」拒绝响应（400 + ENCRYPTION_REQUIRED）。

    用于 release 缺少加密标识、或声明加密但未携带加密体的情况。
    fail-closed：不回退明文，避免加密模式被静默绕过。
    """
    return _failed(400, ErrorCode.ENCRYPT.ENCRYPTION_REQUIRED, I18nKey.ENCRYPT_REQUIRED)


def session_invalid_response() -> JSONResponse:
    """会话失效 / 签名验证失败（401 + SESSION_INVALID）。"""
    return _failed(
        401, ErrorCode.ENCRYPT.SESSION_INVALID, I18nKey.ENCRYPT_SESSION_INVALID
    )


def decryption_failed_response() -> JSONResponse:
    """JSON 请求解密失败（400 + DECRYPTION_FAILED）。"""
    return _failed(
        400, ErrorCode.ENCRYPT.DECRYPTION_FAILED, I18nKey.ENCRYPT_DECRYPTION_FAILED
    )


def meta_decryption_failed_response() -> JSONResponse:
    """FormData meta 解密失败（400 + META_DECRYPT_FAILED）。"""
    return _failed(
        400, ErrorCode.ENCRYPT.META_DECRYPT_FAILED, I18nKey.ENCRYPT_DECRYPTION_FAILED
    )


def replay_response() -> JSONResponse:
    """重放拦截（400 + SIGNATURE_REPLAY_DETECTED）。"""
    return _failed(
        400,
        ErrorCode.ENCRYPT.SIGNATURE_REPLAY_DETECTED,
        I18nKey.ENCRYPT_REPLAY_DETECTED,
    )


def empty_nonce_response() -> JSONResponse:
    """空 nonce 拒绝（400 + EMPTY_NONCE）。"""
    return _failed(400, ErrorCode.ENCRYPT.EMPTY_NONCE, I18nKey.ENCRYPT_EMPTY_NONCE)


def unsupported_version_response(i18n_key: str, i18n_params: dict) -> JSONResponse:
    """加密协议版本不受支持（400 + UNSUPPORTED_VERSION）。"""
    return _failed(400, ErrorCode.ENCRYPT.UNSUPPORTED_VERSION, i18n_key, **i18n_params)


def unsupported_signature_version_response(
    i18n_key: str, i18n_params: dict
) -> JSONResponse:
    """签名协议版本不受支持（400 + UNSUPPORTED_SIGNATURE_VERSION）。"""
    return _failed(
        400,
        ErrorCode.ENCRYPT.UNSUPPORTED_SIGNATURE_VERSION,
        i18n_key,
        **i18n_params,
    )


# ---------------------------------------------------------------------------
# 版本校验
# ---------------------------------------------------------------------------


def check_version_header(client_version: str) -> tuple[str, dict] | None:
    """检查加密版本是否受支持。

    返回 None 表示通过，否则返回 (i18n_key, params)。
    缺失版本视为不合规，拒绝请求。
    """
    if not client_version:
        return I18nKey.ENCRYPT_UNSUPPORTED_VERSION, {
            "version": "",
            "supported": str(sorted(SUPPORTED_ENCRYPTION_VERSIONS)),
        }
    if client_version not in SUPPORTED_ENCRYPTION_VERSIONS:
        return (
            I18nKey.ENCRYPT_UNSUPPORTED_VERSION,
            {
                "version": client_version,
                "supported": str(sorted(SUPPORTED_ENCRYPTION_VERSIONS)),
            },
        )
    return None


def check_signature_version_header(client_version: str) -> tuple[str, dict] | None:
    """检查签名版本是否受支持。

    返回 None 表示通过，否则返回 (i18n_key, params)。
    缺失版本视为不合规，拒绝请求。
    """
    if not client_version:
        return I18nKey.ENCRYPT_UNSUPPORTED_SIG_VERSION, {
            "version": "",
            "supported": str(sorted(SUPPORTED_SIGNATURE_VERSIONS)),
        }
    if client_version not in SUPPORTED_SIGNATURE_VERSIONS:
        return (
            I18nKey.ENCRYPT_UNSUPPORTED_SIG_VERSION,
            {
                "version": client_version,
                "supported": str(sorted(SUPPORTED_SIGNATURE_VERSIONS)),
            },
        )
    return None
