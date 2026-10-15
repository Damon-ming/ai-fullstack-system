# app-server/src/com/damon/ming/ai/summary/base_summarizer.py
from abc import ABC, abstractmethod


class BaseSummarizer(ABC):
    @abstractmethod
    def summarize(self, text: str, max_summary_tokens: int = 800) -> str:
        """
        长文本压缩摘要
        :param text: 原始完整章节文本
        :param max_summary_tokens: 摘要最大token长度
        :return: 压缩后的摘要文本
        """

    @abstractmethod
    def get_model_info(self) -> dict:
        """监控、日志使用"""
