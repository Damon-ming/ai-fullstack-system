"""Embedding 模型 tokenizer 的统一接口包装。"""

from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import (
    BaseTokenizer,
    EmbeddingTokenizerParams,
)


class EmbeddingTokenizer(BaseTokenizer):
    """包装 embedding 模型自带的 tokenizer。

    分块阶段不加入特殊 token；模型推理时由 embedding 模型按自身规则添加。
    """

    def __init__(self, tokenizer):
        super().__init__(
            EmbeddingTokenizerParams(encoding_name=tokenizer.__class__.__name__)
        )
        self._tokenizer = tokenizer

    def encode(self, text: str) -> list[int]:
        return self._tokenizer.encode(text, add_special_tokens=False)

    def decode(self, tokens: list[int]) -> str:
        return self._tokenizer.decode(tokens, skip_special_tokens=True)

    def count_tokens(self, text: str) -> int:
        return len(self.encode(text))

    def get_encoding_name(self) -> str:
        return self.params.encoding_name
