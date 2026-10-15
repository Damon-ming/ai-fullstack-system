# app-server/src/com/damon/ming/ai/registry/embedding_registry.py
from src.com.damon.ming.ai.embedding.factory import EmbeddingFactory
from src.com.damon.ming.ai.embedding.ollama import OllamaEmbedding
from src.com.damon.ming.log import pin

logger = pin("Registry")


def register_all_embeddings():
    """注册所有 embedding provider"""
    EmbeddingFactory.register("ollama", OllamaEmbedding)
    # EmbeddingFactory.register("huggingface", HuggingFaceEmbedding)
    logger.info(f"[Registry] 已注册 providers: {EmbeddingFactory.list_providers()}")
