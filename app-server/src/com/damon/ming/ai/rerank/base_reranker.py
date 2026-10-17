# app-server/src/com/damon/ming/ai/rerank/base_reranker.py
"""
重排器抽象层 —— 纯技术模块，支持多种重排引擎。

提供：
  - BaseReranker:   重排器抽象基类，定义 rerank() 接口
  - RerankerParams: 纯数据类，参数由上层配置注入

配置加载见 ai/config/rerank_config_loader.py，本模块不感知配置来源。

引擎注册表由各实现类通过 @register_reranker 自动注册。
"""

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from llama_index.core.schema import TextNode


@dataclass(frozen=True)
class RerankerParams:
    """重排器参数（纯数据类）。所有参数必须由 YAML 显式声明，无内置默认值。"""

    model_name: str
    max_seq_len: int
    batch_size: int
    device: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseReranker(ABC):
    """重排抽象基类，所有 Reranker 实现遵循统一接口。"""

    def __init__(self, params: RerankerParams):
        self.params = params

    @abstractmethod
    def rerank(
        self,
        query: str,
        nodes: list[TextNode],
        top_k: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[TextNode]:
        """
        对候选文档进行重排序。

        :param query: 用户原始查询
        :param nodes: 召回得到的候选TextNode列表
        :param top_k: 重排后保留多少条；不传则返回全部重排结果
        :param cancel_event: 协作取消信号。实现方应在循环中定期检查，
                            已设置时立即返回空列表（不写入任何分数）。
        :return: 重排后的TextNode（在metadata写入重排分数 _rerank_score）
        """
