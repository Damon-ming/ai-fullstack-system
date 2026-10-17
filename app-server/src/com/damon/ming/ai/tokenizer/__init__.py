# app-server/src/com-damon/ming/ai/tokenizer/__init__.py
"""
分词器抽象层 —— 纯技术模块。

提供：
  - BaseTokenizer:     Token ID 级接口（LLM 上下文管理）
  - BaseWordTokenizer: 词语级接口（BM25 关键词检索）
  - TokenizerParams:   纯数据类，参数由上层配置注入
  - register_engine:   引擎注册装饰器
  - resolve_tokenizer: 根据引擎名称解析实现类

配置加载见 ai/config/tokenizer_config_loader.py，本模块不感知配置来源。

引擎注册表由各实现类通过 @register_engine 自动注册。
"""

from src.com.damon.ming.ai.tokenizer.base_tokenizer import (
    BaseTokenizer,
    BaseWordTokenizer,
    TokenizerParams,
)
from src.com.damon.ming.ai.tokenizer.tiktoken_tokenizer import TiktokenTokenizer

# ── 引擎注册表 ──────────────────────────────────────────────────────
# 支持两种类型："token_id"（BaseTokenizer）和 "word"（BaseWordTokenizer）
_name_to_class: dict[str, type] = {}


def register_engine(name: str):
    """装饰器：将实现类注册到引擎注册表。

    用法：
        @register_engine("tiktoken")
        class TiktokenTokenizer(BaseTokenizer): ...

        @register_engine("jieba")
        class JiebaTokenizer(BaseWordTokenizer): ...
    """

    def decorator(cls):
        if not (issubclass(cls, BaseTokenizer) or issubclass(cls, BaseWordTokenizer)):
            raise TypeError(f"{cls} 必须继承 BaseTokenizer 或 BaseWordTokenizer")
        _name_to_class[name] = cls
        return cls

    return decorator


def resolve_tokenizer(engine: str) -> type:
    """根据引擎名称解析对应的实现类。"""
    if engine not in _name_to_class:
        available = list(_name_to_class.keys())
        raise ValueError(f"未知分词器引擎: '{engine}'. 可用: {available}")
    return _name_to_class[engine]


def list_engines() -> list[str]:
    """列出所有已注册的引擎名称"""
    return list(_name_to_class.keys())


__all__ = [
    "BaseTokenizer",
    "BaseWordTokenizer",
    "TiktokenTokenizer",
    "TokenizerParams",
    "list_engines",
    "register_engine",
    "resolve_tokenizer",
]
