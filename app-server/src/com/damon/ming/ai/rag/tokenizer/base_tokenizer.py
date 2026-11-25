# app-server/src/com/damon/ming/ai/rag/tokenizer/base_tokenizer.py
"""
分词器抽象层 —— 纯技术模块，支持多种分词器引擎。

两种分词器接口：
  - BaseTokenizer:    token ID 级（encode → list[int]），用于 LLM 上下文窗口管理
  - BaseWordTokenizer: 词语级（tokenize → list[str]），用于 BM25 等关键词检索

配置由 AppInitializer 注入，由本模块的 manager 负责装配。

用法：
  from src.com.damon.ming.ai.rag.tokenizer import BaseTokenizer, TokenizerParams, register_engine

  @register_engine("tiktoken")
  class TiktokenTokenizer(BaseTokenizer):
      ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

# ── 参数数据类 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TokenizerParams:
    """Tokenizer 实例的参数基类。"""


@dataclass(frozen=True)
class TiktokenTokenizerParams(TokenizerParams):
    """tiktoken 编码规则参数。"""

    encoding_name: str


@dataclass(frozen=True)
class JiebaTokenizerParams(TokenizerParams):
    """jieba 已解析的用户词典路径。"""

    user_dict_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmbeddingTokenizerParams(TokenizerParams):
    """包装 embedding 模型 tokenizer 时使用的名称。"""

    encoding_name: str


# ── Token ID 级（用于 LLM 上下文管理）──────────────────────────────


class BaseTokenizer(ABC):
    """Token ID 级接口 — 用于上下文管理和按 token 切分文本。"""

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
