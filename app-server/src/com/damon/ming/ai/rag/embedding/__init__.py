# app-server/src/com/damon/ming/ai/rag/embedding/__init__.py
"""
Embedding 服务抽象层与 vLLM、本地 HuggingFace 实现。

Embedding 引擎参数与配置解析均由本模块维护；应用层提供网关地址和模型目录。
"""

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.config import (
    EmbeddingConfig,
    EmbeddingRoleConfig,
    EmbeddingTransportConfig,
)
from src.com.damon.ming.ai.rag.embedding.embedding_gateway import EmbeddingGateway
from src.com.damon.ming.ai.rag.embedding.huggingface import HuggingFaceEmbedding
from src.com.damon.ming.ai.rag.embedding.params import (
    EmbeddingGatewayParams,
    EmbeddingParams,
    HuggingFaceEmbeddingParams,
)
from src.com.damon.ming.ai.rag.embedding.vllm_embedding import VllmEmbedding

__all__ = [
    "BaseEmbeddingService",
    "EmbeddingConfig",
    "EmbeddingGateway",
    "EmbeddingGatewayParams",
    "EmbeddingParams",
    "EmbeddingRoleConfig",
    "EmbeddingTransportConfig",
    "HuggingFaceEmbedding",
    "HuggingFaceEmbeddingParams",
    "VllmEmbedding",
]
