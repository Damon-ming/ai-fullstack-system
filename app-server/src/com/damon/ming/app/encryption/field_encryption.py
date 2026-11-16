"""应用级字段加密器，供各业务存储模块共享。"""

from src.com.damon.ming.encryption.v1.field_encryptor import FieldEncryptor, KeyProvider

_field_encryptor: FieldEncryptor | None = None


def initialize_field_encryptor(key_provider: KeyProvider) -> FieldEncryptor:
    """应用启动时初始化唯一的字段加密器实例。"""
    global _field_encryptor
    _field_encryptor = FieldEncryptor(key_provider)
    return _field_encryptor


def get_field_encryptor() -> FieldEncryptor:
    """获取应用级字段加密器；未初始化时明确报错。"""
    if _field_encryptor is None:
        raise RuntimeError("字段加密器尚未初始化")
    return _field_encryptor
