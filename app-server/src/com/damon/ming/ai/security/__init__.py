# app-server/src/com/damon/ming/ai/security/__init__.py
"""
轻量级输入安全校验 —— guardrail 前置过滤层。

职责：
  - 在调用 LLM 护栏（expensive）之前，用纯本地规则快速拦截无效/恶意输入
  - 规则均为无状态、无 IO、微秒级判定，零额外延迟
  - 不替代 LLM 护栏（语义级检测），只做粗粒度过滤

规则链：
  1. LengthRule       —— 长度上下限（空输入 / 超长攻击）
  2. CharsetRule      —— 异常控制字符检测（二进制注入）
  3. InjectionRule    —— 已知 prompt injection 模式匹配（高频简单攻击）

用法：
  from src.com.damon.ming.ai.security import InputValidator, ValidationResult

  validator = InputValidator()
  result = validator.validate(query)
  if not result.passed:
      return reject_response(result.reason)
"""

from src.com.damon.ming.ai.security.input_validator import (
    InputValidator,
    ValidationResult,
)

__all__ = [
    "InputValidator",
    "ValidationResult",
]
