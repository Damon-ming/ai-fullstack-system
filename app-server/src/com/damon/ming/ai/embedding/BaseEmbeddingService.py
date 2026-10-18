# app-server/src/com/damon/ming/ai/embedding/BaseEmbeddingService.py
"""
Embedding 服务抽象层 —— 纯技术模块。

提供：
  - BaseEmbeddingService:  抽象接口
  - EmbeddingParams:       纯数据类，参数由上层配置注入

配置加载见 ai/config/embedding_config_loader.py，本模块不感知配置来源。

用法：
  from src.com.damon.ming.ai.embedding import BaseEmbeddingService, EmbeddingParams, register_engine

  @register_engine("ollama")
  class OllamaEmbedding(BaseEmbeddingService):
      ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EmbeddingParams:
    """Embedding 参数（纯数据类）。所有参数必须由 YAML 显式声明，无内置默认值。"""

    model_name: str
    base_url: str
    timeout: int
    max_retries: int
    device: str
    normalize_embeddings: bool
    cache_folder: str
    concurrency: int
    """本地推理并发上限（HuggingFace 等线程不安全模型的 batch 并发控制）。
       远程服务（如 Ollama）忽略此值，仅用于线程锁粒度控制。"""
    extra: dict[str, Any] = field(default_factory=dict)


class BaseEmbeddingService(ABC):
    """Embedding 服务抽象基类 — 用于文本向量化"""

    def __init__(self, params: EmbeddingParams):
        self.params = params

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
