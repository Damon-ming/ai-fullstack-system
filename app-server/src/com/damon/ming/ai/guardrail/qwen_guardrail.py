# app-server/src/com/damon/ming/ai/guardrail/qwen_guardrail.py
"""
Qwen 护栏引擎 —— 利用小模型对用户输入进行安全分类。

使用已初始化的推理引擎调用指定模型（如 qwen:0.5b），
通过结构化输出获取 {safe: bool, reason: str} 判定结果。

容错策略：
  - 推理超时时 fail-open（放行），避免护栏故障阻断正常服务
  - 解析异常时同样 fail-open

注册名: "qwen"
"""

import asyncio

from pydantic import BaseModel, ValidationError
from src.com.damon.ming.ai.guardrail import register_engine
from src.com.damon.ming.ai.guardrail.base_guardrail import (
    BaseGuardrail,
    GuardrailParams,
    GuardrailResult,
)
from src.com.damon.ming.ai.inference.base_inference import BaseInferenceService
from src.com.damon.ming.log import pin

logger = pin("QwenGuardrail")

# ── 结构化输出模型 ────────────────────────────────────────────────


class _GuardrailResponse(BaseModel):
    """护栏检测响应结构。"""

    safe: bool
    """输入内容是否安全。true=放行，false=拦截。"""

    reason: str = ""
    """拦截原因说明。"""


# ── 引擎实现 ──────────────────────────────────────────────────────


@register_engine("qwen")
class QwenGuardrail(BaseGuardrail):
    """Qwen 护栏引擎。"""

    def __init__(
        self,
        params: GuardrailParams,
        inference: BaseInferenceService,
    ):
        super().__init__(params)
        self.inference = inference

    async def check(self, query: str) -> GuardrailResult:
        """调用 Qwen 模型检测用户输入。"""
        prompt = self.params.prompt_template.format(query=query)
        messages = [{"role": "user", "content": prompt}]

        logger.debug(
            "护栏检测开始 | model=%s | query_length=%d",
            self.params.model_name,
            len(query),
        )

        try:
            raw = await self.inference.text_generation(
                model_name=self.params.model_name,
                messages=messages,
                response_schema=_GuardrailResponse.model_json_schema(),
                options={"temperature": 0.1},
            )
        except asyncio.CancelledError:
            logger.warning("护栏检测被取消，fail-open 放行")
            return GuardrailResult(passed=True)
        except TimeoutError:
            logger.warning("护栏检测超时，fail-open 放行")
            return GuardrailResult(passed=True)
        except Exception as e:
            logger.warning("护栏检测异常，fail-open 放行 | error=%s", e)
            return GuardrailResult(passed=True)

        return self._parse_response(raw)

    # ── 私有 ────────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> GuardrailResult:
        """解析 LLM 返回的 JSON，提取判定结果。"""
        try:
            data = _GuardrailResponse.model_validate_json(raw)
        except ValidationError as e:
            logger.warning("护栏响应解析失败，fail-open 放行 | error=%s", e)
            return GuardrailResult(passed=True)

        if data.safe:
            logger.debug("护栏检测通过")
            return GuardrailResult(passed=True)

        logger.warning("护栏拦截 | reason=%s", data.reason)
        return GuardrailResult(passed=False, reason=data.reason)
