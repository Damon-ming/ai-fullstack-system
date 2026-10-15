# app-server/src/com/damon/ming/ai/embedding/factory.py
from typing import List

from src.com.damon.ming.ai.embedding.BaseEmbeddingService import BaseEmbeddingService
from src.com.damon.ming.ai.embedding.huggingface import HuggingFaceEmbedding
from src.com.damon.ming.ai.embedding.ollama import OllamaEmbedding
from src.com.damon.ming.log import pin

logger = pin("EmbeddingFactory")

class EmbeddingFactory:
    _providers = {}
    
    @classmethod
    def register(cls, provider_name: str, service_class):
        """注册新的 embedding provider"""
        if not issubclass(service_class, BaseEmbeddingService):
            raise TypeError(f"{service_class} 必须继承 BaseEmbeddingService")
        cls._providers[provider_name] = service_class
        logger.info(f"[EmbeddingFactory] 注册 provider: {provider_name}")
    
    @classmethod
    def create(cls, provider: str, **kwargs) -> BaseEmbeddingService:
        """创建 embedding 实例"""
        if provider not in cls._providers:
            available = list(cls._providers.keys())
            raise ValueError(
                f"不支持的 provider: {provider}. "
                f"可用: {available}"
            )
        return cls._providers[provider](**kwargs)
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """列出所有已注册的 provider"""
        return list(cls._providers.keys())


EmbeddingFactory.register("ollama", OllamaEmbedding)
EmbeddingFactory.register("huggingface", HuggingFaceEmbedding)
