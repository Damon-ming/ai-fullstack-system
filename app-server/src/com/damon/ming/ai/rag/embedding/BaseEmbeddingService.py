# app-server/src/com/damon/ming/ai/rag/embedding/BaseEmbeddingService.py
"""
Embedding 服务接口，只定义上层需要的向量化能力。

模型参数和文本预处理由具体实现与输入策略处理。
"""

from abc import ABC, abstractmethod
from typing import Any

from src.com.damon.ming.app.config.ai.rag.rag_runtime_config_loader import EmbeddingParams


class BaseEmbeddingService(ABC):
    """Embedding 服务抽象基类，用于文本向量化。"""

    def __init__(self, params: EmbeddingParams) -> None:
        self.params = params

    @property
    @abstractmethod
    def max_input_tokens(self) -> int:
        """单条文档可用的最大输入 token 数。"""
        ...

    @property
    def dimension(self) -> int:
        """获取模型输出向量的维度。"""
        return self.params.dimension

    def get_tokenizer(self) -> Any | None:
        """返回模型实际使用的 tokenizer；无法提供时返回 None。"""
        return None

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """向量化查询文本。"""
        ...

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """按输入顺序向量化文档文本。"""
        ...

    @abstractmethod
    def get_model_info(self) -> dict:
        """获取模型信息（用于监控和调试）"""
        ...
