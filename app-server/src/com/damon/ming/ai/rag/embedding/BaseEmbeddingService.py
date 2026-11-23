# app-server/src/com/damon/ming/ai/rag/embedding/BaseEmbeddingService.py
"""
Embedding 服务抽象层 —— 纯技术模块。

提供：
  - BaseEmbeddingService:  抽象接口
  - EmbeddingParams:       参数基类；各引擎使用专门的参数子类

Gateway 角色配置位于 app/config/ai/embedding，RAG 参数位于本模块 config/。
后端通过 EmbeddingParams 接收装配后的参数。

当前 RAG 使用 VllmEmbedding；HuggingFaceEmbedding 可用于本地推理，
由 EmbeddingGateway 按角色提供具体实现。
"""

from abc import ABC, abstractmethod
from typing import Any

from src.com.damon.ming.ai.rag.embedding.model_config import EmbeddingParams


class BaseEmbeddingService(ABC):
    """Embedding 服务抽象基类 — 用于文本向量化"""

    def __init__(self, params: EmbeddingParams):
        self.params = params

    @property
    def max_input_tokens(self) -> int | None:
        """单条文档可用的最大输入 token 数；未知时返回 None。"""
        return None

    def get_tokenizer(self) -> Any | None:
        """返回模型实际使用的 tokenizer；无法提供时返回 None。"""
        return None

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """单条文本向量化"""
        ...

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化"""
        ...

    @abstractmethod
    def get_model_info(self) -> dict:
        """获取模型信息（用于监控和调试）"""
        ...
