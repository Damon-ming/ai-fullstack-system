# app-server/src/com/damon/ming/ai/registry/db_registry.py
from src.com.damon.ming.ai.vector_db.chroma_store import ChromaDBStore
from src.com.damon.ming.ai.vector_db.factory import VectorStoreFactory
from src.com.damon.ming.ai.vector_db.pgvector_store import PGVectorStore
from src.com.damon.ming.log import pin

logger = pin("db_registry")


def register_all_vector_dbs():
    """注册所有向量存储 provider"""
    VectorStoreFactory.register("chromadb", ChromaDBStore)
    VectorStoreFactory.register("pgvector", PGVectorStore)
    logger.info(f"[Registry] 已注册向量存储: {VectorStoreFactory.list_providers()}")
