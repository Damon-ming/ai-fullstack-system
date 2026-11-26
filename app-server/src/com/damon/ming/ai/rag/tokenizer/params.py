"""Runtime parameters for tokenizer implementations."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class TokenizerParams:
    """Tokenizer 实例的参数基类。"""


@dataclass(frozen=True, kw_only=True)
class TiktokenTokenizerParams(TokenizerParams):
    """tiktoken 编码规则参数。"""

    encoding_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.encoding_name, str) or not self.encoding_name.strip():
            raise ValueError("encoding_name 必须是非空字符串")


@dataclass(frozen=True, kw_only=True)
class JiebaTokenizerParams(TokenizerParams):
    """jieba 已解析的用户词典路径。"""

    user_dict_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.user_dict_paths, tuple) or not all(
            isinstance(path, str) and path.strip() for path in self.user_dict_paths
        ):
            raise TypeError("user_dict_paths 必须是非空路径字符串组成的元组")


@dataclass(frozen=True, kw_only=True)
class EmbeddingTokenizerParams(TokenizerParams):
    """包装 embedding 模型 tokenizer 时使用的名称。"""

    encoding_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.encoding_name, str) or not self.encoding_name.strip():
            raise ValueError("encoding_name 必须是非空字符串")


@dataclass(frozen=True, kw_only=True)
class TokenizerRoleParams:
    """供装配器使用的引擎标识与已解析参数。"""

    tokenizer_engine: str
    params: TokenizerParams

    def __post_init__(self) -> None:
        if (
            not isinstance(self.tokenizer_engine, str)
            or not self.tokenizer_engine.strip()
        ):
            raise ValueError("tokenizer_engine 必须是非空字符串")
        expected_type = {
            "tiktoken": TiktokenTokenizerParams,
            "jieba": JiebaTokenizerParams,
        }.get(self.tokenizer_engine)
        if expected_type is None:
            raise ValueError(f"未支持的分词器引擎: {self.tokenizer_engine}")
        if not isinstance(self.params, expected_type):
            raise TypeError(
                f"{self.tokenizer_engine} 必须使用 {expected_type.__name__}"
            )
