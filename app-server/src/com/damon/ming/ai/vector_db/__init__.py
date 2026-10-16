# app-server/src/com/damon/ming/ai/vector_db/__init__.py
"""
向量存储抽象层 —— 纯技术模块。

提供：
  - BaseVectorStore:   抽象接口
  - VectorStoreParams: 纯数据类，参数由上层配置注入
  - resolve_store:     根据引擎名称解析对应的实现类

配置加载见 ai/config/vector_config_loader.py，本模块不感知配置来源。

引擎注册表（_name_to_class）由各实现类在模块导入时自动注册。
新增 vector_db 只需：写实现类 → 加 @register_engine("name") 装饰器。
"""

from src.com.damon.ming.ai.vector_db.base_vector_db import (
    BaseVectorStore,
    VectorStoreParams,
)
from src.com.damon.ming.ai.vector_db.chroma_store import ChromaDBStore

# ── 引擎注册表 ──────────────────────────────────────────────────────
# 引擎名称 → 实现类，各实现类通过 @register_engine 自动注册
_name_to_class: dict[str, type[BaseVectorStore]] = {}


def register_engine(name: str):
    """装饰器：将实现类注册到引擎注册表。

    用法：
        @register_engine("chroma")
        class ChromaDBStore(BaseVectorStore):
            ...
    """

    def decorator(cls: type[BaseVectorStore]):
        if not issubclass(cls, BaseVectorStore):
            raise TypeError(f"{cls} 必须继承 BaseVectorStore")
        _name_to_class[name] = cls
        return cls

    return decorator


def resolve_store(engine: str) -> type[BaseVectorStore]:
    """根据引擎名称解析对应的实现类。

    Args:
        engine: 引擎名称，如 "chroma" / "pgvector"

    Returns:
        BaseVectorStore 的子类

    Raises:
        ValueError: 未注册的引擎名称
    """
    if engine not in _name_to_class:
        available = list(_name_to_class.keys())
        raise ValueError(f"未知引擎: '{engine}'. 可用: {available}")
    return _name_to_class[engine]


def list_engines() -> list[str]:
    """列出所有已注册的引擎名称"""
    return list(_name_to_class.keys())


__all__ = [
    "BaseVectorStore",
    "ChromaDBStore",
    "VectorStoreParams",
    "list_engines",
    "register_engine",
    "resolve_store",
]
