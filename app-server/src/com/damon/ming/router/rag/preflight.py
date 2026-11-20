# app-server/src/com/damon/ming/router/rag/preflight.py
"""
推理前检查 —— 输入校验 + 护栏检测（chat 链路专用）。

从 rag_router 抽出的前置检查，供 /rag/answer/v1 与 /rag/stream/v1 复用：
  - check_input:                  纯本地规则，零 IO，微秒级，拦无效/攻击输入
  - check_guardrail:              护栏 LLM 检测 + 独立超时
                                     （超时返回错误响应）

返回 BaseLLMFailedResponse 表示被拦截（data.error_msg 即用户可见文案），
返回 None 表示放行。拦截响应的错误码区分来源：
  CHAT.INPUT_BLOCKED      本地输入校验
  CHAT.GUARDRAIL_BLOCKED  护栏 LLM
"""

import asyncio

import httpx
from openai import APITimeoutError
from pydantic import BaseModel
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import get_locale, t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.i18n.locale_negotiator import get_default_locale
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.rag.failure import chat_failure
from src.com.damon.ming.router.rag.schemas.response import BaseLLMFailedResponse
from src.com.damon.ming.router.rag.security import InputValidator

logger = pin("chat.preflight")

# 轻量级输入校验器（模块级单例，无状态，可并发）
_input_validator = InputValidator()


class _GuardrailResponse(BaseModel):
    safe: bool
    reason: str = ""


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


async def check_guardrail(app_state, query: str) -> BaseLLMFailedResponse | None:
    """执行护栏检测，超时返回错误，其他异常交由路由层处理。"""
    locales = app_state.ai.rag.locales
    locale_config = locales.get(get_locale()) or locales[get_default_locale()]
    try:
        raw = await app_state.ai.inference.gateway.get("guardrail").generate(
            messages=[
                {"role": "system", "content": locale_config.guardrail_prompt},
                {"role": "user", "content": query},
            ],
            response_schema=_GuardrailResponse.model_json_schema(),
        )
    except asyncio.CancelledError:
        raise
    except (TimeoutError, APITimeoutError, httpx.TimeoutException):
        logger.warning("护栏检测超时，返回超时错误")
        return chat_failure(ErrorCode.CHAT.TIMEOUT, t(I18nKey.CHAT_TIMEOUT))
    result = _GuardrailResponse.model_validate_json(raw)

    if not result.safe:
        logger.warning("护栏拦截用户输入 | reason=%s", result.reason)
        return chat_failure(
            ErrorCode.CHAT.GUARDRAIL_BLOCKED,
            result.reason or t(I18nKey.GUARDRAIL_BLOCKED),
        )
    return None
