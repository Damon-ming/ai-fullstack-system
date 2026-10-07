# app-server/src/com/damon/ming/encryption/globals.py
"""
加密模块的全局状态（KeyManager 实例 + 签名密钥）。

为什么单独一个文件？
  - middleware.py 会导入 crypto_engine / key_management / signature
  - 如果全局变量放在其中任一文件，都会形成"被导入者反导入导入者"的循环
  - 拆成 globals.py 后：所有子模块 → globals（单向），无循环

放在 encryption/ 内部而不是更上层，是因为这些状态是加密体系自身的内部实现细节，
上层（main.py / middleware / router）通过本模块的函数来读写，不直接触碰变量。
"""

from src.com.damon.ming.encryption.key_management import KeyManager

_key_manager: KeyManager | None = None
_signature_secret: str = ""


def get_key_manager() -> KeyManager:
    """获取全局 KeyManager 实例。"""
    if _key_manager is None:
        raise RuntimeError(
            "KeyManager not initialized. Call set_key_manager() in lifespan."
        )
    return _key_manager


def set_key_manager(km: KeyManager) -> None:
    """设置全局 KeyManager 实例（在 lifespan 中调用一次）。"""
    global _key_manager
    _key_manager = km


def get_signature_secret() -> str:
    """获取当前签名密钥。"""
    return _signature_secret


def set_signature_secret(secret: str) -> None:
    """设置签名密钥（在 lifespan 中调用一次）。"""
    global _signature_secret
    _signature_secret = secret
