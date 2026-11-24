# app-server/src/com/damon/ming/ai/rag/tokenizer/jieba_tokenizer.py

import os
import unicodedata

from src.com.damon.ming.ai.rag.tokenizer import register_engine
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import (
    BaseWordTokenizer,
    JiebaTokenizerParams,
)
from src.com.damon.ming.log import pin

logger = pin("JiebaTokenizer")


@register_engine("jieba")
class JiebaTokenizer(BaseWordTokenizer):
    """jieba 词语分词器 — 适用于 BM25 等中文关键词检索场景

    支持通过 YAML 注入自定义词典，提升领域术语切分准确性。
    用户词典路径由配置加载器解析后注入。
    """

    def __init__(self, params: JiebaTokenizerParams):
        super().__init__(params)
        try:
            import jieba
        except ImportError:
            raise ImportError("请安装 jieba: pip install jieba")
        self.jieba = jieba
        self._load_custom_dicts(params.user_dict_paths)

    @staticmethod
    def _is_punctuation_or_whitespace(word: str) -> bool:
        """识别纯 Unicode 标点或空白词项。"""
        return all(
            char.isspace() or unicodedata.category(char).startswith("P")
            for char in word
        )

    def _load_custom_dicts(self, user_dict_paths: tuple[str, ...]) -> None:
        """加载配置加载器已解析的 jieba 用户词典路径。"""
        for path in user_dict_paths:
            if not os.path.isfile(path):
                logger.warning(f"jieba 词典文件不存在，已跳过: {path}")
                continue
            self.jieba.load_userdict(path)
            logger.info(f"JiebaTokenizer 加载自定义词典: {path}")

    def tokenize(self, text: str) -> list[str]:
        """中文词语切分，过滤标点和空字符串"""
        words = self.jieba.lcut(text.strip())
        return [
            word
            for word in words
            if word.strip() and not self._is_punctuation_or_whitespace(word)
        ]
