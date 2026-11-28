# app-server/src/com/damon/ming/ai/rag/rerank/base_reranker.py
"""
重排器抽象层 —— 纯技术模块，支持多种重排引擎。

提供：
  - BaseReranker:   重排器抽象基类，定义 rerank() 接口
  - RerankerParams: 纯数据类，参数由上层配置注入

配置由 AppInitializer 注入，manager 负责装配。

引擎注册表由各实现类通过 @register_reranker 自动注册。
"""

import threading
from abc import ABC, abstractmethod

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.rag.rerank.params import RerankerParams


class BaseReranker(ABC):
    """重排抽象基类，所有 Reranker 实现遵循统一接口。"""

    def __init__(self, params: RerankerParams):
        self.params = params

    @abstractmethod
    def rerank(
        self,
        query: str,
        nodes: list[TextNode],
        cancel_event: threading.Event | None = None,
    ) -> list[TextNode]:
        """
        对候选文档进行重排序。

        :param query: 用户原始查询
        :param nodes: 召回得到的候选TextNode列表
        :param cancel_event: 协作取消信号。实现方应在循环中定期检查，
                            已设置时立即返回空列表（不写入任何分数）。
        :return: 重排后的TextNode（在metadata写入重排分数 _rerank_score）
        """
