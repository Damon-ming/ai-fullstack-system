# app-server/src/com/damon/ming/ai/inference/base_inference.py
"""
推理服务抽象层 —— 纯技术模块，支持多种推理引擎。

提供：
  - BaseInferenceService: 推理服务抽象基类
  - StreamToken: 流式输出 token
  - InferenceParams: 纯数据类，参数由上层配置注入
  - register_engine: 引擎注册装饰器
  - resolve_engine: 根据引擎名称解析实现类

配置加载见 config/rag/，本模块不感知配置来源。

引擎注册表由各实现类通过 @register_engine 自动注册。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

# StreamToken.type 取值 —— 流式 token 类型标识
STREAM_TYPE_REASONING = "reasoning"
STREAM_TYPE_CONTENT = "content"


@dataclass
class StreamToken:
    """流式输出的带标签 token —— 区分 reasoning 与 content。"""

    content: str
    type: str = STREAM_TYPE_CONTENT  # STREAM_TYPE_REASONING | STREAM_TYPE_CONTENT


@dataclass(frozen=True)
class InferenceParams:
    """推理引擎参数（纯数据类）。所有参数必须由 YAML 显式声明，无内置默认值。

    仅包含引擎级（连接）参数。
    模型级参数（temperature / top_p / num_ctx）在 YAML 的 models 层配置，
    调用时通过 options 传入。

    无服务端重试：异常直接抛给上层，由前端自行重试请求。
    """

    base_url: str
    timeout: float
    api_key: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelOptions:
    """模型级推理参数。从 YAML models 层读取，调用时传入。"""

    temperature: float
    top_p: float
    num_ctx: int


class BaseInferenceService(ABC):
    """推理服务统一抽象，Ollama/VLLM/第三方大模型统一接口。"""

    def __init__(self, params: InferenceParams):
        self.params = params

    @abstractmethod
    async def text_generation(
        self,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        model_name: str = "",
    ) -> str:
        """一次性返回完整文本/结构化JSON。

        response_schema 用于需要结构化输出的场景（如护栏判定）；
        聊天正文不传，返回纯文本。
        model_name 由角色配置传入，网关仅路由，不负责注入模型名。
        """

    @abstractmethod
    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        reason: bool = False,
        options: dict[str, Any] | None = None,
        model_name: str = "",
    ) -> AsyncGenerator[StreamToken, None]:
        """流式SSE输出 —— 产出 StreamToken 区分 reasoning / content。

        推理走模型原生通道（reasoning_content / thinking），正文为纯文本，
        不做 JSON 约束。model_name 由角色配置传入。
        """

    async def warmup(self, model_name: str) -> None:
        """可选模型预热钩子。"""

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """监控、日志模型信息。"""


# ── 引擎注册表 ──────────────────────────────────────────────────────
_name_to_class: dict[str, type[BaseInferenceService]] = {}


def register_engine(name: str):
    """装饰器：将实现类注册到引擎注册表。"""

    def decorator(cls):
        if not issubclass(cls, BaseInferenceService):
            raise TypeError(f"{cls} 必须继承 BaseInferenceService")
        _name_to_class[name] = cls
        return cls

    return decorator


def resolve_engine(engine: str) -> type[BaseInferenceService]:
    """根据引擎名称解析对应的实现类。"""
    if engine not in _name_to_class:
        available = list(_name_to_class.keys())
        raise ValueError(f"未知推理引擎: '{engine}'. 可用: {available}")
    return _name_to_class[engine]


def list_engines() -> list[str]:
    """列出所有已注册的引擎名称。"""
    return list(_name_to_class.keys())
