"""向量存储的初始化和业务模型访问入口。"""

from src.com.damon.ming.ai.vector_db import resolve_store
from src.com.damon.ming.ai.vector_db.base_vector_db import (
    SharedVectorStoreParams,
    VectorStoreParams,
)
from src.com.damon.ming.ai.vector_db.config.vector_config_loader import (
    VectorConfigLoader,
)
from src.com.damon.ming.ai.vector_db.pgvector_store import PGVectorStore


class VectorStoreManager:
    def __init__(self) -> None:
        self._pgvector: PGVectorStore | None = None

    def initialize(self, embedding_dimension: int, vector_db_url: str) -> None:
        if self._pgvector is not None:
            raise RuntimeError("向量存储已经初始化")

        config = VectorConfigLoader().load("pgvector", vector_db_url=vector_db_url)
        params = VectorStoreParams(
            shared_params=SharedVectorStoreParams(
                table_name=config.table_name,
                embedding_dimension=embedding_dimension,
            ),
            engine_params=config.engine_params,
        )
        store_class = resolve_store(config.engine)
        store = store_class(params)
        if not isinstance(store, PGVectorStore):
            raise TypeError("pgvector 配置没有创建 PGVectorStore")
        self._pgvector = store

    def get_pgvector(self) -> PGVectorStore:
        if self._pgvector is None:
            raise RuntimeError("向量存储尚未初始化")
        return self._pgvector
