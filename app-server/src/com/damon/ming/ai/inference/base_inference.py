# app-server/src/com/damon/ming/ai/inference/base_inference.py
"""
推理服务统一抽象，Ollama/VLLM/第三方大模型统一接口。

流式输出使用 StreamToken 区分推理过程与正文：
  StreamToken(type="reasoning", content="...")  —— 推理过程
  StreamToken(type="content",   content="...")  —— 正文回答
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamToken:
    """流式输出的带标签 token —— 区分 reasoning 与 content。"""

    content: str
    type: str = "content"  # "reasoning" | "content"


class BaseInferenceService(ABC):
    """推理服务统一抽象，Ollama/VLLM/第三方大模型统一接口"""

    @abstractmethod
    async def text_generation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """一次性返回完整文本/结构化JSON"""

    @abstractmethod
    async def stream_generate(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamToken, None]:
        """流式SSE输出 —— 产出 StreamToken 区分 reasoning / content"""

    @abstractmethod
    async def check_model_ready(self, model_name: str) -> bool:
        """检测模型是否存在/服务就绪"""

    async def warmup(self, model_name: str) -> None:
        """可选模型预热钩子。"""

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """监控、日志模型信息"""
