# app-server/src/com/damon/ming/ai/reranker/base_reranker.py
from abc import ABC, abstractmethod

from llama_index.core.schema import TextNode


class BaseReranker(ABC):
    """重排抽象基类，所有Reranker实现遵循统一接口"""

    @abstractmethod
    def rerank(
        self, query: str, nodes: list[TextNode], top_k: int | None = None
    ) -> list[TextNode]:
        """
        对候选文档进行重排序
        :param query: 用户原始查询
        :param nodes: 召回得到的候选TextNode列表
        :param top_k: 重排后保留多少条；不传则返回全部重排结果
        :return: 重排后的TextNode（建议在metadata写入重排分数 _rerank_score）
        """
