# app-server/src/com/damon/ming/ai/tokenizer/base_tokenizer.py
from abc import ABC, abstractmethod


class BaseTokenizer(ABC):
    """分词器统一抽象接口"""

    @abstractmethod
    def encode(self, text: str) -> list[int]:
        """文本转token id列表"""

    @abstractmethod
    def decode(self, tokens: list[int]) -> str:
        """token id列表还原文本"""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """统计文本token数量"""

    @abstractmethod
    def get_encoding_name(self) -> str:
        """返回当前分词器编码名称"""
