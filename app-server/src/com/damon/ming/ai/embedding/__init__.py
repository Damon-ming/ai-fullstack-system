# app-server/src/com/damon/ming/ai/embedding/__init__.py

from src.com.damon.ming.ai.embedding.BaseEmbeddingService import BaseEmbeddingService
from src.com.damon.ming.ai.embedding.config import EmbeddingConfig
from src.com.damon.ming.ai.embedding.factory import EmbeddingFactory
from src.com.damon.ming.ai.embedding.huggingface import HuggingFaceEmbedding
from src.com.damon.ming.ai.embedding.ollama import OllamaEmbedding

__all__ = [
    "BaseEmbeddingService",
    "EmbeddingConfig",
    "EmbeddingFactory",
    "HuggingFaceEmbedding",
    "OllamaEmbedding"
]