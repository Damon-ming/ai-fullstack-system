# app-server/src/com/damon/ming/ai/tokenizer/jieba_tokenizer.py

import os
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
    """jieba 词语分词器 — 适用于 BM25 等中文关键词检索场景

    支持通过 YAML 注入自定义词典，提升领域术语切分准确性。
    dicts_base_dir + dict_paths 直接使用，不做路径转换。
    """

    def __init__(self, params: TokenizerParams):
        super().__init__(params)
        try:
            import jieba
        except ImportError:
            raise ImportError("请安装 jieba: pip install jieba")
        self.jieba = jieba
        # 加载自定义词典（配置驱动，dict_paths 在 params.extra 中）
        self._load_custom_dicts(params.extra)
        # 过滤纯标点、空字符串
        self._punct_pattern = re.compile(r"^[\s\p{P}]+$", re.UNICODE)

    def _load_custom_dicts(self, extra: dict) -> None:
        """加载 jieba 自定义词典。

        dicts_base_dir 由 loader 解析为绝对路径后注入 TokenizerParams，
        dict_paths 从 extra 读取，不做路径转换。
        缺失文件仅警告不中断，保证服务可用性。
        """
        dict_paths = extra.get("dict_paths", [])
        if not dict_paths:
            return
        base_dir = self.params.dicts_base_dir
        for path in dict_paths:
            full_path = os.path.join(base_dir, path) if base_dir else path
            if not os.path.isfile(full_path):
                logger.warning(f"jieba 词典文件不存在，已跳过: {full_path}")
                continue
            self.jieba.load_userdict(full_path)
            logger.info(f"JiebaTokenizer 加载自定义词典: {full_path}")

    def tokenize(self, text: str) -> list[str]:
        """中文词语切分，过滤标点和空字符串"""
        words = self.jieba.lcut(text.strip())
        return [w for w in words if w.strip() and not self._punct_pattern.match(w)]
