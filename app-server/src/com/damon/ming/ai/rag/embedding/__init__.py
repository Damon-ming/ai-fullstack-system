# app-server/src/com/damon/ming/ai/rag/embedding/__init__.py
"""
Embedding 服务抽象层与 vLLM、本地 HuggingFace 实现。

Gateway 角色配置在 app/config/ai/embedding；RAG 参数在本模块 config/。
后端装配由 AppInitializer 调用配置加载器完成。
"""

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.ai.rag.embedding.embedding_gateway import EmbeddingGateway
from src.com.damon.ming.ai.rag.embedding.huggingface import HuggingFaceEmbedding
from src.com.damon.ming.ai.rag.embedding.vllm import VllmEmbedding

__all__ = [
    "BaseEmbeddingService",
    "EmbeddingGateway",
    "EmbeddingParams",
    "HuggingFaceEmbedding",
    "VllmEmbedding",
]
