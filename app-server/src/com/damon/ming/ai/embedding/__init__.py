# app-server/src/com/damon/ming/ai/embedding/__init__.py
"""
Embedding 服务抽象层 —— 纯技术模块。

提供：
  - BaseEmbeddingService: 抽象接口
  - EmbeddingParams:      纯数据类，参数由上层配置注入
  - register_engine:      引擎注册装饰器
  - resolve_embedding:    根据引擎名称解析实现类

配置加载见 ai/config/embedding_config_loader.py，本模块不感知配置来源。
"""

from src.com.damon.ming.ai.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.ai.embedding.huggingface import HuggingFaceEmbedding
from src.com.damon.ming.ai.embedding.ollama import OllamaEmbedding

# ── 引擎注册表 ──────────────────────────────────────────────────────
_name_to_class: dict[str, type] = {}


def register_engine(name: str):
    """装饰器：将实现类注册到引擎注册表。

    用法：
        @register_engine("ollama")
        class OllamaEmbedding(BaseEmbeddingService): ...
    """

    def decorator(cls):
        if not issubclass(cls, BaseEmbeddingService):
            raise TypeError(f"{cls} 必须继承 BaseEmbeddingService")
        _name_to_class[name] = cls
        return cls

    return decorator


def resolve_embedding(engine: str) -> type:
    """根据引擎名称解析对应的实现类。"""
    if engine not in _name_to_class:
        available = list(_name_to_class.keys())
        raise ValueError(f"未知 embedding 引擎: '{engine}'. 可用: {available}")
    return _name_to_class[engine]


def list_engines() -> list[str]:
    """列出所有已注册的引擎名称"""
    return list(_name_to_class.keys())


__all__ = [
    "BaseEmbeddingService",
    "EmbeddingParams",
    "HuggingFaceEmbedding",
    "OllamaEmbedding",
    "list_engines",
    "register_engine",
    "resolve_embedding",
]
