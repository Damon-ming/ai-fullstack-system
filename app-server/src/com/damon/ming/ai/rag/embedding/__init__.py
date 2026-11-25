# app-server/src/com/damon/ming/ai/rag/embedding/__init__.py
"""
Embedding 服务抽象层与 vLLM、本地 HuggingFace 实现。

Embedding 角色配置与引擎参数在 app/config/ai/rag/rag_runtime_config_loader.py。
应用层提供模型配置，具体后端由 embedding 模块装配。
"""

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.embedding_gateway import EmbeddingGateway
from src.com.damon.ming.ai.rag.embedding.huggingface import HuggingFaceEmbedding
from src.com.damon.ming.app.config.ai.rag.rag_runtime_config_loader import (
    EmbeddingParams,
    HuggingFaceEmbeddingParams,
    VLLMEmbeddingParams,
)
from src.com.damon.ming.ai.rag.embedding.vllm_embedding import VllmEmbedding

__all__ = [
    "BaseEmbeddingService",
    "EmbeddingGateway",
    "EmbeddingParams",
    "HuggingFaceEmbedding",
    "HuggingFaceEmbeddingParams",
    "VLLMEmbeddingParams",
    "VllmEmbedding",
]
