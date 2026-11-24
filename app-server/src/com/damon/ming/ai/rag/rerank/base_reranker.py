# app-server/src/com/damon/ming/ai/rag/rerank/base_reranker.py
"""
重排器抽象层 —— 纯技术模块，支持多种重排引擎。

提供：
  - BaseReranker:   重排器抽象基类，定义 rerank() 接口
  - RerankerParams: 纯数据类，参数由上层配置注入

配置加载见 rerank/config/，由本模块的 manager 负责装配。

引擎注册表由各实现类通过 @register_reranker 自动注册。
"""

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from llama_index.core.schema import TextNode


@dataclass(frozen=True)
class RerankerParams:
    """重排器参数（纯数据类）。"""

    model_name: str
    max_seq_len: int
    batch_size: int
    # 滑动窗口：长节点切窗打分后按 max 聚合
    window_overlap: int
    max_windows_per_node: int
    # 打分时是否附加章节标题链（heading_path），必须由 YAML 显式声明
    include_heading: bool
    device: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name 必须是非空字符串")
        if type(self.max_seq_len) is not int or self.max_seq_len <= 0:
            raise ValueError("max_seq_len 必须是正整数")
        if type(self.batch_size) is not int or self.batch_size <= 0:
            raise ValueError("batch_size 必须是正整数")
        if type(self.window_overlap) is not int or self.window_overlap < 0:
            raise ValueError("window_overlap 必须是非负整数")
        if (
            type(self.max_windows_per_node) is not int
            or self.max_windows_per_node <= 0
        ):
            raise ValueError("max_windows_per_node 必须是正整数")
        if not isinstance(self.include_heading, bool):
            raise TypeError("include_heading 必须是布尔值")


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
