# app-server/src/com/damon/ming/ai/rag/embedding/__init__.py
"""
Embedding 服务抽象层与 vLLM、本地 HuggingFace 实现。

Embedding 引擎参数与实现均由本模块维护；应用层负责从运行时配置构造参数。
"""

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.embedding_gateway import EmbeddingGateway
from src.com.damon.ming.ai.rag.embedding.huggingface import HuggingFaceEmbedding
from src.com.damon.ming.ai.rag.embedding.params import (
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
