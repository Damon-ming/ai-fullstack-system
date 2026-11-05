# app-server/src/com/damon/ming/router/chat/preflight.py
"""
推理前检查 —— 输入校验 + 护栏检测（chat 链路专用）。

从 chat_router 抽出的前置检查，供同步 /send/v1 与流式 /chat/v1 复用：
  - check_input:                  纯本地规则，零 IO，微秒级，拦无效/攻击输入
  - check_guardrail_with_timeout: 护栏 LLM 检测 + 独立超时 + 信号量限流
                                     （超时 fail-open 放行）

返回 BaseLLMFailedResponse 表示被拦截（data.error_msg 即用户可见文案），
返回 None 表示放行。拦截响应的错误码区分来源：
  CHAT.INPUT_BLOCKED      本地输入校验
  CHAT.GUARDRAIL_BLOCKED  护栏 LLM
"""

import asyncio

from src.com.damon.ming.ai.schemas.response import BaseLLMFailedResponse
from src.com.damon.ming.ai.security import InputValidator
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.chat.failure import chat_failure

logger = pin("chat.preflight")

# 轻量级输入校验器（模块级单例，无状态，可并发）
_input_validator = InputValidator()


def check_input(query: str) -> BaseLLMFailedResponse | None:
    """前置输入校验（纯本地规则，零 IO，微秒级）。

    在调用 LLM 护栏之前快速拦截无效/攻击性输入，避免浪费护栏推理资源。
    校验通过返回 None，不通过返回失败响应。
    """
    result = _input_validator.validate(query)
    if not result.passed:
        logger.warning(
            "输入校验拦截 | i18n_key=%s | reason=%s", result.i18n_key, result.reason
        )
        return chat_failure(
            ErrorCode.CHAT.INPUT_BLOCKED,
            t(result.i18n_key, **result.i18n_params),
        )
    return None


async def _check_guardrail(app_state, query: str) -> BaseLLMFailedResponse | None:
    """执行护栏检测，不通过时返回失败响应，通过时返回 None。"""
    guardrail = getattr(app_state, "guardrail", None)
    if guardrail is None:
        return None

    result = await guardrail.check(query)
    if not result.passed:
        logger.warning("护栏拦截用户输入 | reason=%s", result.reason)
        return chat_failure(
            ErrorCode.CHAT.GUARDRAIL_BLOCKED,
            result.reason or t(I18nKey.GUARDRAIL_BLOCKED),
        )
    return None


async def check_guardrail_with_timeout(
    app_state, query: str
) -> BaseLLMFailedResponse | None:
    """护栏检测 + 独立超时 + 信号量限流（超时 fail-open 放行）。

    guardrail_sem 保护护栏 LLM 调用不被打爆。
    """
    guardrail_timeout = app_state.guardrail_timeout
    guardrail_sem = getattr(app_state, "guardrail_sem", None)
    try:
        async with asyncio.timeout(guardrail_timeout):
            if guardrail_sem is not None:
                async with guardrail_sem:
                    return await _check_guardrail(app_state, query)
            else:
                return await _check_guardrail(app_state, query)
    except TimeoutError:
        logger.warning("护栏检测超时，fail-open 放行 | timeout=%ds", guardrail_timeout)
        return None
