# app-server/src/com/damon/ming/ai/security/input_validator.py
"""
轻量级输入校验器 —— 纯本地规则，零 IO，微秒级判定。

设计原则：
  - 所有规则无状态、可并发调用，无需加锁
  - 规则链顺序排列，命中即返回（短路求值），不做冗余检查
  - 不替代 LLM 护栏——仅过滤明显无效/攻击性输入，语义安全仍由护栏负责
  - 参数硬编码（规则本身是安全策略，非业务配置，不应被外部调整）
"""

import re
from dataclasses import dataclass

from src.com.damon.ming.log import pin

logger = pin("security.validator")


# ── 校验结果 ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationResult:
    """单条校验结果。"""

    passed: bool
    """是否通过校验。True=放行，False=拦截。"""

    reason: str = ""
    """拦截原因（仅 passed=False 时有意义）。"""

    rule: str = ""
    """命中的规则名（便于日志追踪）。"""


# ── 规则引擎 ──────────────────────────────────────────────────────────


# Prompt injection 高频模式（仅匹配最明显的简单攻击）
# 不覆盖编码绕过、角色扮演变体、多语言混淆等复杂注入（由 LLM 护栏兜底）
_INJECTION_PATTERNS = [
    # 英文常见注入指令
    re.compile(r"ignore\s+(previous|all|above|prior)", re.IGNORECASE),
    re.compile(r"disregard\s+(instructions?|rules?|prompts?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.IGNORECASE),
    re.compile(r"new\s+persona", re.IGNORECASE),
    re.compile(r"^\s*system\s*:\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\s*/\s*instruction\s*>", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    # 中文常见注入指令
    re.compile(r"忽略(之前|以上|先前|上面)(的)?(指令|规则|要求|设定)"),
    re.compile(r"你(现在|以后)是(一个|一名|the)"),
    re.compile(r"扮演(一个|一名|模式)"),
    re.compile(r"进入(DAN|开发者|越狱|debug)\s*模式"),
]


def _check_length(query: str) -> ValidationResult:
    """长度校验：空输入拒绝，超长输入拒绝（资源保护）。"""
    if not query or len(query.strip()) == 0:
        return ValidationResult(
            passed=False, reason="输入内容不能为空", rule="LengthRule"
        )
    if len(query) > 8000:
        return ValidationResult(
            passed=False,
            reason="输入内容过长，请精简后重试（上限 8000 字符）",
            rule="LengthRule",
        )
    return ValidationResult(passed=True)


def _check_charset(query: str) -> ValidationResult:
    """字符集校验：拦截含 null byte 或异常控制字符的输入。

    这是粗粒度字符层过滤，不覆盖编码绕过、多语言混淆等语义级攻击（由 LLM 护栏兜底）。
    """
    # null byte 检测（文本协议中不应出现）
    if "\x00" in query:
        return ValidationResult(
            passed=False, reason="输入包含非法字符", rule="CharsetRule"
        )
    # 控制字符检测：任何非 \n\r\t 的控制字符都拒绝
    ctrl_count = sum(1 for ch in query if ord(ch) < 32 and ch not in "\n\r\t")
    if ctrl_count > 0:
        return ValidationResult(
            passed=False, reason="输入包含异常字符", rule="CharsetRule"
        )
    return ValidationResult(passed=True)


def _check_injection(query: str) -> ValidationResult:
    """Prompt injection 模式匹配：仅拦截最明显的简单攻击。"""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query):
            logger.warning(
                "注入模式匹配拦截 | pattern=%s | query_prefix=%.50s",
                pattern.pattern,
                query,
            )
            return ValidationResult(
                passed=False,
                reason="输入包含不允许的内容模式",
                rule="InjectionRule",
            )
    return ValidationResult(passed=True)


# ── 校验器 ────────────────────────────────────────────────────────────


class InputValidator:
    """轻量级输入校验器 —— 规则链顺序执行，短路求值。

    所有规则纯本地计算，无 IO，微秒级完成。
    线程安全：规则函数无状态，可并发调用。

    用法：
        validator = InputValidator()
        result = validator.validate(user_input)
        if not result.passed:
            return reject(result.reason)
    """

    # 规则链顺序：成本从低到高排列，命中即短路
    _rules = (_check_length, _check_charset, _check_injection)

    def validate(self, query: str) -> ValidationResult:
        """执行全量规则校验。

        Args:
            query: 用户原始输入。

        Returns:
            ValidationResult，passed=True 表示通过全部规则。
        """
        for rule_fn in self._rules:
            result = rule_fn(query)
            if not result.passed:
                logger.warning(
                    "输入校验拦截 | rule=%s | reason=%s | query_length=%d",
                    result.rule,
                    result.reason,
                    len(query),
                )
                return result
        return ValidationResult(passed=True)
