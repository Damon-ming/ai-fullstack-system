# app-server/src/com/damon/ming/ai/vector_db/factory.py

from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.log import pin


class VectorStoreFactory:
    """
    向量存储工厂

    支持动态注册和创建不同类型的向量存储
    """

    _providers: dict[str, type[BaseVectorStore]] = {}

    @classmethod
    def register(cls, provider_name: str, store_class: type[BaseVectorStore]):
        """注册新的向量存储"""
        if not issubclass(store_class, BaseVectorStore):
            raise TypeError(f"{store_class} 必须继承 BaseVectorStore")
        cls._providers[provider_name] = store_class
        logger = pin("VectorStoreFactory")
        logger.info(f"[VectorStoreFactory] 注册 provider: {provider_name}")

    @classmethod
    def create(cls, provider: str, **kwargs) -> BaseVectorStore:
        """创建向量存储实例"""
        if provider not in cls._providers:
            available = list(cls._providers.keys())
            raise ValueError(f"不支持的 provider: {provider}. 可用: {available}")
        return cls._providers[provider](**kwargs)

    @classmethod
    def list_providers(cls) -> list:
        """列出所有已注册的 provider"""
        return list(cls._providers.keys())
