# app-server/src/com/damon/ming/ai/rag/embedding/__init__.py
"""
Embedding 服务抽象层与 vLLM、本地 HuggingFace 实现。

Embedding 引擎参数与配置解析均由本模块维护；应用层提供网关地址及已展开路径的配置。
"""

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.config import EmbeddingConfig
from src.com.damon.ming.ai.rag.embedding.embedding_gateway import EmbeddingGateway
from src.com.damon.ming.ai.rag.embedding.huggingface import HuggingFaceEmbedding
from src.com.damon.ming.ai.rag.embedding.params import (
    EmbeddingGatewayParams,
    EmbeddingParams,
    EmbeddingRoleParams,
    HuggingFaceEmbeddingParams,
)
from src.com.damon.ming.ai.rag.embedding.vllm_embedding import VllmEmbedding

__all__ = [
    "BaseEmbeddingService",
    "EmbeddingConfig",
    "EmbeddingGateway",
    "EmbeddingGatewayParams",
    "EmbeddingParams",
    "EmbeddingRoleParams",
    "HuggingFaceEmbedding",
    "HuggingFaceEmbeddingParams",
    "VllmEmbedding",
]
