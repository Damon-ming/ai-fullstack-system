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

# 配置路径基准目录：从 tokenizer/ 向上回溯两级到 src/com/damon/ming/
# 与 rag_tool.py 中 KNOWLEDGES_DIR = Path(__file__).resolve().parent.parent / "knowledges" 一致
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@register_engine("jieba")
class JiebaTokenizer(BaseWordTokenizer):
    """jieba 词语分词器 — 适用于 BM25 等中文关键词检索场景

    支持通过 params.extra.dict_paths 注入自定义词典，提升领域术语切分准确性。
    词典路径相对于项目根目录解析，缺失文件仅警告不中断。
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
        """从 extra.dict_paths 加载 jieba 自定义词典。

        路径支持相对路径（基于项目根目录解析）和绝对路径。
        缺失文件仅警告不中断，保证服务可用性。
        """
        dict_paths = extra.get("dict_paths", [])
        if not dict_paths:
            return
        for path in dict_paths:
            abs_path = (
                path if os.path.isabs(path) else os.path.join(_PROJECT_ROOT, path)
            )
            if not os.path.isfile(abs_path):
                logger.warning(f"jieba 词典文件不存在，已跳过: {path}")
                continue
            self.jieba.load_userdict(abs_path)
            logger.info(f"JiebaTokenizer 加载自定义词典: {path}")

    def tokenize(self, text: str) -> list[str]:
        """中文词语切分，过滤标点和空字符串"""
        words = self.jieba.lcut(text.strip())
        return [w for w in words if w.strip() and not self._punct_pattern.match(w)]
