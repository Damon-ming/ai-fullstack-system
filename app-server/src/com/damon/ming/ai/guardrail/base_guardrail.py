# app-server/src/com/damon/ming/ai/guardrail/base_guardrail.py
"""
护栏抽象层 —— 纯技术模块，支持多种护栏引擎。

职责：
  - 对用户输入进行安全检测（暴力/色情/违法/仇恨言论等）
  - 检测不通过时阻止后续 RAG + LLM 流程，直接返回前端

引擎接口极简：check(query) -> GuardrailResult。
具体引擎（Qwen / 关键词黑名单等）各自实现检测逻辑。

护栏引擎复用推理引擎（guardrail 角色），模型由 gateway 路由决定
（api_key → vLLM 实例），配置中不包含模型信息。

配置见 ai/config/guardrail/guardrail-config.yaml，本模块不感知配置来源。

用法：
  from src.com.damon.ming.ai.guardrail import BaseGuardrail, GuardrailParams, register_engine

  @register_engine("qwen-guardrail")
  class QwenGuardrail(BaseGuardrail):
      ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

# ── 检测结果 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class GuardrailResult:
    """护栏检测结果。"""

    passed: bool
    """是否通过检测。True=放行，False=拦截。"""

    reason: str = ""
    """拦截原因（仅 passed=False 时有意义），直接返回前端展示。"""


# ── 参数数据类 ────────────────────────────────────────────────────


@dataclass(frozen=True)
class GuardrailParams:
    """护栏参数（纯数据类）。所有参数必须由 YAML 显式声明，无内置默认值。

    护栏引擎复用已初始化的推理引擎，模型由 gateway 路由决定
    （api_key → vLLM 实例 → 实例加载的模型），因此 params 不包含模型信息，
    只包含护栏自身的检测 prompt。
    """

    prompt_template: str
    """检测 prompt 模板，接收 {query} 占位符。"""


# ── 抽象基类 ──────────────────────────────────────────────────────


class BaseGuardrail(ABC):
    """护栏引擎抽象基类。

    具体引擎需实现 check() 方法，内部调用推理服务完成检测。
    护栏引擎持有推理服务引用（由初始化阶段注入），不自行创建连接。
    """

    def __init__(self, params: GuardrailParams):
        self.params = params

    @abstractmethod
    async def check(self, query: str) -> GuardrailResult:
        """对用户输入执行安全检测。

        Args:
            query: 用户原始输入文本。

        Returns:
            GuardrailResult，passed=True 放行，passed=False 拦截。
        """
        ...
