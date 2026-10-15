# app-server/src/com/damon/ming/ai/rewrite/base_rewriter.py

from abc import ABC, abstractmethod
from typing import Any


class BaseQueryRewriter(ABC):
    @abstractmethod
    def rewrite(
        self, query: str, context: str | None = None, max_tokens: int = 256
    ) -> str:
        """
        用户查询改写/提炼，生成适合向量检索的问句
        :param query: 用户原始问句
        :param context: 多轮上文上下文（可选，用于补全指代）
        :param max_tokens: 改写后最大长度限制
        :return: 优化后的检索query
        """

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """监控日志使用"""
