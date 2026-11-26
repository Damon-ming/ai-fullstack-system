# app-server/src/com/damon/ming/ai/rag/rerank/__init__.py
"""
重排器抽象层 —— 纯技术模块。

提供：
  - BaseReranker:   重排器抽象基类，定义 rerank() 接口
  - RerankerParams: 纯数据类，参数由上层配置注入
  - register_reranker: 引擎注册装饰器
  - resolve_reranker:  根据引擎名称解析实现类
  - list_engines:     列出所有已注册的引擎名称

配置由 AppInitializer 注入，manager 负责装配。

引擎注册表由各实现类通过 @register_reranker 自动注册。
"""

from pathlib import Path

from src.com.damon.ming.ai.rag.rerank.base_reranker import (
    BaseReranker,
)
from src.com.damon.ming.ai.rag.rerank.config import RerankConfig
from src.com.damon.ming.ai.rag.rerank.params import RerankerParams

# ── 引擎注册表（必须在实现类 import 之前定义）──────────────────────
_name_to_class: dict[str, type[BaseReranker]] = {}


def register_reranker(name: str):
    """装饰器：将实现类注册到引擎注册表。"""

    def decorator(cls):
        if not issubclass(cls, BaseReranker):
            raise TypeError(f"{cls} 必须继承 BaseReranker")
        _name_to_class[name] = cls
        return cls

    return decorator


def resolve_reranker(engine: str) -> type[BaseReranker]:
    """根据引擎名称解析对应的实现类。"""
    if engine not in _name_to_class:
        available = list(_name_to_class.keys())
        raise ValueError(f"未知重排引擎: '{engine}'. 可用: {available}")
    return _name_to_class[engine]


def list_engines() -> list[str]:
    """列出所有已注册的引擎名称。"""
    return list(_name_to_class.keys())


# ── 触发注册（必须放在注册器定义之后）──────────────────────────────
from src.com.damon.ming.ai.rag.rerank.cross_encoder_reranker import CrossEncoderReranker


def create_rerankers(model_root_dir: Path, config: dict[str, object]):
    """初始化并返回重排器管理器。"""
    from src.com.damon.ming.ai.rag.rerank.manager import RerankersManager

    manager = RerankersManager()
    manager.initialize(model_root_dir, config)
    return manager


__all__ = [
    "BaseReranker",
    "CrossEncoderReranker",
    "RerankConfig",
    "RerankerParams",
    "create_rerankers",
    "list_engines",
    "register_reranker",
    "resolve_reranker",
]
