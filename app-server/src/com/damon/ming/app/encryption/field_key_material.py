# app-server/src/com/damon/ming/app/encryption/field_key_material.py
"""字段加密和盲索引所用的应用密钥材料。"""

from src.com.damon.ming.app.encryption.field_key_store import PgFieldKeyStore
from src.com.damon.ming.encryption.constants import AES_KEY_SIZES, INDEX_KEY_SIZE
from src.com.damon.ming.encryption.v1.field_encryptor import KeyProvider
from src.com.damon.ming.exception import EncryptionError
from src.com.damon.ming.log import pin

logger = pin("app.encryption.field_key_material")


class KeyMaterial(KeyProvider):
    """从数据库加载并缓存数据加密密钥和盲索引密钥。"""

    def __init__(self, key_store: PgFieldKeyStore) -> None:
        if key_store is None:
            raise ValueError("字段加密密钥存储不能为空")
        self._key_store = key_store
        self._data_key: bytes | None = None
        self._index_key = b""

    def initialize(self) -> None:
        """从数据库读取密钥；首次启动时生成、持久化后再载入缓存。"""
        data_key, index_key = self._key_store.load_or_create()
        if len(data_key) not in AES_KEY_SIZES:
            raise ValueError("数据库中的字段数据密钥长度无效")
        if len(index_key) != INDEX_KEY_SIZE:
            raise ValueError("数据库中的盲索引密钥长度无效")
        self._data_key = data_key
        self._index_key = index_key

    def get_data_key(self) -> bytes:
        """获取缓存的数据加密密钥。"""
        if self._data_key is None:
            raise EncryptionError(
                "KeyMaterial not initialized. Call initialize() first."
            )
        return self._data_key

    def get_index_key(self) -> bytes:
        """获取缓存的盲索引密钥。"""
        if not self._index_key:
            raise EncryptionError(
                "KeyMaterial not initialized. Call initialize() first."
            )
        return self._index_key
