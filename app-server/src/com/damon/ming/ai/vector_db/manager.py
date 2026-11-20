"""向量存储的初始化和业务模型访问入口。"""

from src.com.damon.ming.ai.vector_db.config.vector_config_loader import (
    VectorConfigLoader,
)
from src.com.damon.ming.ai.vector_db.pgvector_store import PGVectorStore


class VectorStoreManager:
    def __init__(self) -> None:
        self._pgvector: PGVectorStore | None = None

    def initialize(self) -> None:
        if self._pgvector is not None:
            raise RuntimeError("向量存储已经初始化")
        store = VectorConfigLoader().load("pgvector")
        if not isinstance(store, PGVectorStore):
            raise TypeError("pgvector 配置没有创建 PGVectorStore")
        self._pgvector = store

    def get_pgvector(self) -> PGVectorStore:
        if self._pgvector is None:
            raise RuntimeError("向量存储尚未初始化")
        return self._pgvector
