# app-server/src/com/damon/ming/ai/inference/base_inference.py
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class BaseInferenceService(ABC):
    """推理服务统一抽象，Ollama/VLLM/第三方大模型统一接口"""

    @abstractmethod
    async def text_generation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        think_flag: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """一次性返回完整文本/结构化JSON"""

    @abstractmethod
    async def stream_generate(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式SSE输出"""

    @abstractmethod
    async def check_model_ready(self, model_name: str) -> bool:
        """检测模型是否存在/服务就绪"""

    async def warmup(self, model_name: str) -> None:
        """可选模型预热钩子。"""

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """监控、日志模型信息"""
