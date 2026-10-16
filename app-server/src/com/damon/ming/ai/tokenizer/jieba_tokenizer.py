# app-server/src/com/damon/ming/ai/tokenizer/jieba_tokenizer.py

import re

from src.com.damon.ming.ai.tokenizer import register_engine
from src.com.damon.ming.ai.tokenizer.base_tokenizer import (
    BaseWordTokenizer,
    TokenizerParams,
)
from src.com.damon.ming.log import pin

logger = pin("JiebaTokenizer")


@register_engine("jieba")
class JiebaTokenizer(BaseWordTokenizer):
    """jieba 词语分词器 — 适用于 BM25 等中文关键词检索场景"""

    def __init__(self, params: TokenizerParams):
        super().__init__(params)
        try:
            import jieba
        except ImportError:
            raise ImportError("请安装 jieba: pip install jieba")
        self.jieba = jieba
        # 过滤纯标点、空字符串
        self._punct_pattern = re.compile(r"^[\s\p{P}]+$", re.UNICODE)

    def tokenize(self, text: str) -> list[str]:
        """中文词语切分，过滤标点和空字符串"""
        words = self.jieba.lcut(text.strip())
        return [w for w in words if w.strip() and not self._punct_pattern.match(w)]
