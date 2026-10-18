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
import threading
import time
from collections import deque

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

# ── 护栏健康监控 ─────────────────────────────────────────────────
# 滑动时间窗口计数器：记录最近 WINDOW 秒内的 fail-open 次数，
# 超阈值时输出告警（便于运维感知护栏异常）。
# 多 worker 部署时各进程独立计数，未来升级可替换为 Redis Sorted Set。
_FAIL_OPEN_ALERT_THRESHOLD = 5
_FAIL_OPEN_WINDOW_SECONDS = 60  # 时间窗口（秒）
_fail_open_timestamps: deque[float] = deque()
_fail_open_lock = threading.Lock()


def _record_fail_open(reason: str) -> None:
    """记录一次 fail-open 事件，窗口内连续超阈值时输出告警。"""
    now = time.monotonic()
    with _fail_open_lock:
        _fail_open_timestamps.append(now)
        # 滑动窗口：移除窗口外的旧记录
        cutoff = now - _FAIL_OPEN_WINDOW_SECONDS
        while _fail_open_timestamps and _fail_open_timestamps[0] < cutoff:
            _fail_open_timestamps.popleft()
        count = len(_fail_open_timestamps)
    if count >= _FAIL_OPEN_ALERT_THRESHOLD:
        logger.warning(
            "护栏连续 fail-open 告警 | 窗口内次数=%d | 窗口=%ds | 最近原因=%s | 请检查护栏模型是否正常",
            count,
            _FAIL_OPEN_WINDOW_SECONDS,
            reason,
        )


def _record_guardrail_success() -> None:
    """护栏正常工作时清理窗口外的旧 fail-open 记录。

    仅淘汰超龄记录，不清空窗口内记录。避免间歇性故障（偶发超时+偶尔成功）
    导致计数器永远达不到告警阈值。窗口内的真实故障密度得以保留。
    """
    now = time.monotonic()
    with _fail_open_lock:
        cutoff = now - _FAIL_OPEN_WINDOW_SECONDS
        while _fail_open_timestamps and _fail_open_timestamps[0] < cutoff:
            _fail_open_timestamps.popleft()


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
        prompt = self.params.prompt_template.replace("{query}", query, 1)
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
            _record_fail_open("cancelled")
            return GuardrailResult(passed=True)
        except TimeoutError:
            logger.warning("护栏检测超时，fail-open 放行")
            _record_fail_open("timeout")
            return GuardrailResult(passed=True)
        except Exception as e:
            logger.warning("护栏检测异常，fail-open 放行 | error=%s", e)
            _record_fail_open(str(e))
            return GuardrailResult(passed=True)

        # 推理成功：重置连续 fail-open 计数器
        _record_guardrail_success()
        return self._parse_response(raw)

    # ── 私有 ────────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> GuardrailResult:
        """解析 LLM 返回的 JSON，提取判定结果。"""
        try:
            data = _GuardrailResponse.model_validate_json(raw)
        except ValidationError as e:
            logger.warning("护栏响应解析失败，fail-open 放行 | error=%s", e)
            _record_fail_open(f"parse_error: {e}")
            return GuardrailResult(passed=True)

        if data.safe:
            logger.debug("护栏检测通过")
            return GuardrailResult(passed=True)

        logger.warning("护栏拦截 | reason=%s", data.reason)
        return GuardrailResult(passed=False, reason=data.reason)
