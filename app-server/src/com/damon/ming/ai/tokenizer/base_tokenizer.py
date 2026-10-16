# app-server/src/com/damon/ming/ai/tokenizer/base_tokenizer.py
"""
分词器抽象层 —— 纯技术模块，支持多种分词器引擎。

两种分词器接口：
  - BaseTokenizer:    token ID 级（encode → list[int]），用于 LLM 上下文窗口管理
  - BaseWordTokenizer: 词语级（tokenize → list[str]），用于 BM25 等关键词检索

配置见 ai/config/tokenizer-config.yaml，本模块不感知配置来源。

用法：
  from src.com.damon.ming.ai.tokenizer import BaseTokenizer, TokenizerParams, register_engine

  @register_engine("tiktoken")
  class TiktokenTokenizer(BaseTokenizer):
      ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# ── 参数数据类 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TokenizerParams:
    """
    分词器参数（纯数据类）。

    通用字段：
      encoding_name: 编码名称（tiktoken 用）

    扩展字段：
      extra: 各引擎特有参数透传
    """

    encoding_name: str = "cl100k_base"
    extra: dict[str, Any] = field(default_factory=dict)


# ── Token ID 级（用于 LLM 上下文管理）──────────────────────────────


class BaseTokenizer(ABC):
    """Token ID 级分词器 — 用于 LLM 上下文窗口计数、文本截断"""

    def __init__(self, params: TokenizerParams):
        self.params = params

    @abstractmethod
    def encode(self, text: str) -> list[int]:
        """文本转 token id 列表"""
        ...

    @abstractmethod
    def decode(self, tokens: list[int]) -> str:
        """token id 列表还原文本"""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """统计文本 token 数量"""
        ...

    @abstractmethod
    def get_encoding_name(self) -> str:
        """返回当前分词器编码名称"""
        ...


# ── 词语级（用于 BM25 关键词检索）─────────────────────────────────


class BaseWordTokenizer(ABC):
    """词语级分词器 — 用于 BM25 等需要词语切分的场景"""

    def __init__(self, params: TokenizerParams):
        self.params = params

    @abstractmethod
    def tokenize(self, text: str) -> list[str]:
        """文本转词语列表"""
        ...
