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
    """
    Embedding 参数（纯数据类）。

    通用字段：
      model_name: 模型名称
      timeout: 请求超时秒数

    Ollama 特有：
      base_url: Ollama 服务地址
      max_retries: 重试次数

    HuggingFace 特有：
      device: 推理设备（cpu / cuda）
      normalize_embeddings: 是否归一化
      cache_folder: 模型缓存目录
    """

    model_name: str = "bge-m3"
    timeout: int = 60

    # Ollama
    base_url: str = "http://localhost:11434"
    max_retries: int = 3

    # HuggingFace
    device: str = "cpu"
    normalize_embeddings: bool = True
    cache_folder: str = ""

    # 扩展
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
