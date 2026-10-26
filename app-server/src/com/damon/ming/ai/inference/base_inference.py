# app-server/src/com/damon/ming/ai/inference/base_inference.py
"""
推理服务抽象层 —— 纯技术模块，支持多种推理引擎。

提供：
  - BaseInferenceService: 推理服务抽象基类
  - StreamToken: 流式输出 token
  - InferenceParams: 纯数据类，参数由上层配置注入
  - register_engine: 引擎注册装饰器
  - resolve_engine: 根据引擎名称解析实现类

配置加载见 config/inference/，本模块不感知配置来源。

引擎注册表由各实现类通过 @register_engine 自动注册。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamToken:
    """流式输出的带标签 token —— 区分 reasoning 与 content。"""

    content: str
    type: str = "content"  # "reasoning" | "content"


@dataclass(frozen=True)
class InferenceParams:
    """推理引擎参数（纯数据类）。所有参数必须由 YAML 显式声明，无内置默认值。

    仅包含引擎级（连接）参数。
    模型级参数（temperature / top_p / num_ctx）在 YAML 的 models 层配置，
    调用时通过 options 传入。

    无服务端重试：异常直接抛给上层，由前端自行重试请求。
    """

    base_url: str
    timeout: int
    api_key: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelOptions:
    """模型级推理参数。从 YAML models 层读取，调用时传入。"""

    temperature: float = 0.1
    top_p: float = 0.9
    num_ctx: int = 4096


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

        model_name 可空：API Gateway 模式下由 gateway 自动注入。
        """

    @abstractmethod
    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        model_name: str = "",
    ) -> AsyncGenerator[StreamToken, None]:
        """流式SSE输出 —— 产出 StreamToken 区分 reasoning / content。

        response_schema 不为 None 时，LLM 输出结构化 JSON（前端在 done 事件后解析）。
        model_name 可空：API Gateway 模式下由 gateway 自动注入。
        """

    @abstractmethod
    async def check_model_ready(self, model_name: str) -> bool:
        """检测模型是否存在/服务就绪。"""

    async def warmup(self, model_name: str) -> None:
        """可选模型预热钩子。"""

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """监控、日志模型信息。"""

    # ── 辅助任务：意图识别 / 查询改写 ──────────────────────────────

    async def classify_intention(
        self,
        model_name: str,
        query: str,
        intention_list: list[str],
        extra_instruction: str | None = None,
    ) -> str:
        """意图分类。

        Args:
            model_name: 意图识别模型名称
            query: 用户原始提问
            intention_list: 可选意图列表
            extra_instruction: 额外业务约束指令

        Returns:
            识别出的意图名称（intention_list 内的值）
        """
        prompt = (
            f"你是意图分类器，**只能输出一个意图名称，禁止额外文字、解释、标点**。\n"
            f"可选意图列表：{','.join(intention_list)}\n"
            f"{extra_instruction or ''}\n"
            f"用户问题：{query}\n"
            f"直接输出意图名称："
        )
        result = await self.text_generation(
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.0},
        )
        pred = result.strip()
        if pred not in intention_list:
            from src.com.damon.ming.log import pin

            pin("Intention").warning(
                f"意图不在允许列表 | query={query} | output={pred}"
            )
        return pred

    async def rewrite_query(
        self,
        model_name: str,
        query: str,
        context: str | None = None,
        max_tokens: int = 256,
    ) -> str:
        """查询改写/提炼。

        Args:
            model_name: 改写模型名称
            query: 用户原始问句
            context: 多轮上文上下文（可选）
            max_tokens: 改写后最大长度

        Returns:
            优化后的检索 query
        """
        if context and context.strip():
            prompt = (
                f"结合历史对话上下文，优化用户当前提问，补全指代、消除歧义。\n"
                f"只输出最终检索问句，禁止额外说明。\n"
                f"【历史上下文】\n{context}\n"
                f"【用户当前问题】\n{query}\n"
                f"优化检索问句："
            )
        else:
            prompt = (
                f"你是查询优化器，从用户原始描述提炼核心检索问题。\n"
                f"剔除情绪、铺垫、无关闲聊，保留实体、条件、疑问目标。\n"
                f"输出精简问句，不要解释、不要多余标点。\n"
                f"原始文本：\n{query}\n"
                f"优化检索问句："
            )
        return await self.text_generation(
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
        )


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
