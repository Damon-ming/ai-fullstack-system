# app-server/src/com/damon/ming/ai/tokenizer/tiktoken_tokenizer.py

import tiktoken
from src.com.damon.ming.ai.tokenizer import register_engine
from src.com.damon.ming.ai.tokenizer.base_tokenizer import (
    BaseTokenizer,
    TokenizerParams,
)
from src.com.damon.ming.log import pin

logger = pin("TiktokenTokenizer")


@register_engine("tiktoken")
class TiktokenTokenizer(BaseTokenizer):
    """tiktoken 分词器 — 适用于 OpenAI/GPT 系列模型的 token 计数"""

    def __init__(self, params: TokenizerParams):
        super().__init__(params)
        self.enc = tiktoken.get_encoding(params.encoding_name)

    def encode(self, text: str) -> list[int]:
        return self.enc.encode(text)

    def decode(self, tokens: list[int]) -> str:
        return self.enc.decode(tokens)

    def count_tokens(self, text: str) -> int:
        return len(self.encode(text))

    def get_encoding_name(self) -> str:
        return self.params.encoding_name
