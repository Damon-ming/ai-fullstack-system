# app-server/src/com/damon/ming/ai/guardrail/__init__.py
"""
护栏模块注册表 —— 引擎自注册 + 解析接口。

添加新护栏引擎：
  1. 新建引擎类，继承 BaseGuardrail
  2. 使用 @register_engine("name") 装饰器
  3. 在本文件底部 import 引擎类（触发注册）
"""

from src.com.damon.ming.ai.guardrail.base_guardrail import (
    BaseGuardrail,
)

# ── 注册表（必须在实现类 import 之前定义）────────────────────────
_name_to_class: dict[str, type[BaseGuardrail]] = {}


def register_engine(name: str):
    """护栏引擎注册装饰器。

    使用方式：
        @register_engine("qwen-guardrail")
        class QwenGuardrail(BaseGuardrail):
            ...

    装饰时校验继承关系并加入注册表。
    """

    def decorator(cls: type[BaseGuardrail]):
        if not issubclass(cls, BaseGuardrail):
            raise TypeError(f"{cls.__name__} 必须继承 BaseGuardrail 才能注册为护栏引擎")
        _name_to_class[name] = cls
        return cls

    return decorator


def resolve_guardrail(engine: str) -> type[BaseGuardrail]:
    """根据引擎名解析护栏实现类。"""
    if engine not in _name_to_class:
        raise ValueError(
            f"未知护栏引擎: '{engine}'，可用引擎: {list(_name_to_class.keys())}"
        )
    return _name_to_class[engine]


def list_engines() -> list[str]:
    """列出所有已注册的护栏引擎名。"""
    return list(_name_to_class.keys())


# ── 触发注册（必须放在注册器定义之后）──────────────────────────────
from src.com.damon.ming.ai.guardrail.qwen_guardrail import QwenGuardrail

__all__ = [
    "BaseGuardrail",
    "QwenGuardrail",
    "list_engines",
    "register_engine",
    "resolve_guardrail",
]
