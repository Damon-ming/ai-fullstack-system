# app-server/src/com/damon/ming/encryption/globals.py
"""
加密模块的全局状态（KeyManager 实例）。

为什么单独一个文件？
  - middleware.py 会导入 crypto_engine / key_management / signature
  - 如果全局变量放在其中任一文件，都会形成"被导入者反导入导入者"的循环
  - 拆成 globals.py 后：所有子模块 → globals（单向），无循环

放在 encryption/ 内部而不是更上层，是因为这些状态是加密体系自身的内部实现细节，
上层（main.py / middleware / router）通过本模块的函数来读写，不直接触碰变量。
"""

from src.com.damon.ming.encryption.v1.key_management import KeyManager
from src.com.damon.ming.exception import EncryptionError

_key_manager: KeyManager | None = None
_sign_context: bytes = b""  # HKDF 派生签名密钥的 context，由业务层注入

# 服务端支持的加密协议版本集合（中间件校验 X-Encrypt-Version header）
SUPPORTED_ENCRYPTION_VERSIONS = frozenset({"v1"})

# 服务端支持的签名协议版本集合（中间件校验 X-Signature-Version header）
SUPPORTED_SIGNATURE_VERSIONS = frozenset({"v1"})


def get_key_manager() -> KeyManager:
    """获取全局 KeyManager 实例。"""
    if _key_manager is None:
        from src.com.damon.ming.exception.error_codes import ErrorCode

        raise EncryptionError(
            "KeyManager not initialized. Call set_key_manager() in lifespan.",
            biz_code=ErrorCode.SYSTEM.ENCRYPTION_FAILURE,
        )
    return _key_manager


def set_key_manager(km: KeyManager) -> None:
    """设置全局 KeyManager 实例（在 lifespan 中调用一次）。"""
    global _key_manager
    _key_manager = km


def get_sign_context() -> bytes:
    """获取 HKDF 签名密钥派生 context。"""
    return _sign_context


def set_sign_context(context: bytes) -> None:
    """
    设置 HKDF 签名密钥派生 context（在 lifespan 中调用一次）。

    此值由业务层配置（如 YAML）注入，encryption 模块本身不包含该常量。
    """
    global _sign_context
    _sign_context = context
