# app-server/src/com/damon/ming/ai/embedding/BaseEmbeddingService.py
from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingService(ABC):
    """Embedding 服务抽象基类"""
    
    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """单条文本向量化"""
        pass
    
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量文本向量化"""
        pass
    
    @abstractmethod
    def get_model_info(self) -> dict:
        """获取模型信息（用于监控和调试）"""
        pass