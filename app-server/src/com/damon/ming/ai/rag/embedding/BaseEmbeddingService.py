# app-server/src/com/damon/ming/ai/rag/embedding/BaseEmbeddingService.py
"""
Embedding 服务抽象层 —— 纯技术模块。

提供：
  - BaseEmbeddingService:  抽象接口
  - EmbeddingParams:       通用参数数据类；引擎专属参数放在 extra

配置加载见 embedding/config/，由本模块的 manager 负责装配。

用法：
  from src.com.damon.ming.ai.rag.embedding import BaseEmbeddingService, EmbeddingParams, register_engine

  @register_engine("ollama")
  class OllamaEmbedding(BaseEmbeddingService):
      ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EmbeddingParams:
    """Embedding 通用参数；引擎专属参数由 extra 承载。"""

    model_name: str
    extra: dict[str, Any] = field(default_factory=dict)


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
