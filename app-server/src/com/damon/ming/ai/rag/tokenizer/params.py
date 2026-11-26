"""Runtime parameters for tokenizer implementations."""

from dataclasses import dataclass


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
