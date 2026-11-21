# app-server/src/com/damon/ming/ai/rag/summary/summary_service.py
"""
摘要服务 —— 封装所有 LLM 摘要压缩能力，与 reconstruction 解耦。

职责：
  - 单文本摘要（含分段和容错）
  - 不持有线程池，纯 asyncio 并发

取消策略：
  - 不感知取消——由上层 RagChoreographer 通过 asyncio.CancelledError 统一处理
  - run_summary 中的 await 点被 CancelledError 自然中断
  - 中断时直接抛弃所有中间结果（副本、压缩文本等），不做任何保存/恢复
"""

import asyncio
from math import floor

from src.com.damon.ming.ai.inference.base_inference import ContextWindowExceededError
from src.com.damon.ming.ai.inference.inference_gateway import RoleInference
from src.com.damon.ming.ai.rag.summary.config.summary_config_loader import (
    SummaryConfig,
)
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.log import pin

logger = pin("SummaryService")


class SummaryService:
    """摘要压缩服务，纯技术模块，不含业务逻辑。"""

    def __init__(
        self,
        tokenizer: BaseTokenizer,
        summary_inference: RoleInference,
        config: SummaryConfig,
    ):
        self.tokenizer = tokenizer
        self.summary_inference = summary_inference
        self.config = config

    # ── 公开接口 ──────────────────────────────────────────────────────

    async def run_summary(self, text: str, max_tokens: int) -> str:
        """单文本摘要压缩。超长自动分段，失败降级硬截断。"""
        if max_tokens <= 0:
            raise ValueError("摘要输出目标 max_tokens 必须大于 0")

        num_ctx = self.summary_inference.context_window()
        system_prompt = self._build_system_prompt(max_tokens)
        prompt_tokens = self.tokenizer.count_tokens(system_prompt)
        margin_ratio = self.config.context_margin_ratio
        prompt_limit = floor((num_ctx - max_tokens) / (1 + margin_ratio))
        input_limit = prompt_limit - prompt_tokens
        text_tokens = self.tokenizer.count_tokens(text)

        if input_limit <= 0:
            logger.warning(
                "摘要模型窗口不足，降级到硬截断 | 窗口=%d | 提示词=%d | 输出目标=%d | 余量比例=%.2f%%",
                num_ctx,
                prompt_tokens,
                max_tokens,
                margin_ratio * 100,
            )
            return self.truncate_by_token(text, max_tokens)

        if text_tokens > input_limit:
            logger.info(
                "摘要选择分段流程 | 输入tokens=%d | 输入上限=%d | 摘要目标=%d",
                text_tokens,
                input_limit,
                max_tokens,
            )
            return await self._run_segmented_summary(text, max_tokens, input_limit)

        logger.info(
            "摘要选择单段流程 | 输入tokens=%d | 输入上限=%d | 摘要目标=%d",
            text_tokens,
            input_limit,
            max_tokens,
        )
        return await self._run_single_summary(text, max_tokens)

    def truncate_by_token(self, text: str, max_tokens: int) -> str:
        """按 token 数硬截断文本。"""
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.tokenizer.decode(tokens[:max_tokens])

    # ── 私有：摘要实现 ────────────────────────────────────────────────

    def _build_system_prompt(self, max_tokens: int) -> str:
        return self.config.system_prompt_template.replace(
            "{max_tokens}", str(max_tokens), 1
        )

    def _build_messages(self, text: str, max_tokens: int) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._build_system_prompt(max_tokens)},
            {"role": "user", "content": text},
        ]

    async def _run_single_summary(self, text: str, max_tokens: int) -> str:
        """单段摘要，带容错降级。"""
        messages = self._build_messages(text, max_tokens)
        # max_tokens 为通用输出上限键，由推理层按引擎翻译（vLLM 直用 / Ollama → num_predict）。
        # 目标值覆盖角色默认值，保证摘要长度受调用方控制。
        try:
            return await self.summary_inference.generate(
                messages=messages,
                options={"max_tokens": max_tokens},
            )
        except asyncio.CancelledError:
            logger.warning("_run_single_summary | 摘要生成被取消")
            raise
        except Exception as e:
            if isinstance(e, ContextWindowExceededError):
                logger.warning("摘要后端返回上下文超限，直接硬截断")
            else:
                logger.warning(f"摘要生成失败，降级到硬截断 | error={e}")
            return self.truncate_by_token(text, max_tokens)

    async def _run_segmented_summary(
        self, text: str, max_tokens: int, segment_size: int
    ) -> str:
        """将超长文本分段摘要，再合并结果。"""
        segments = self._split_by_tokens(text, segment_size)
        logger.info(
            f"文本超长({self.tokenizer.count_tokens(text)}tokens)，"
            f"分{len(segments)}段摘要 | segment_size={segment_size}"
        )

        per_segment_max = max(max_tokens // len(segments), 1)
        tasks = [
            self._run_single_summary(segment, per_segment_max) for segment in segments
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        summaries: list[str] = []
        for i, r in enumerate(results):
            if isinstance(r, asyncio.CancelledError):
                raise r
            if isinstance(r, Exception):
                logger.warning(f"第{i + 1}/{len(segments)}段摘要失败，跳过: {r}")
                continue
            summaries.append(r)

        if not summaries:
            logger.warning("全部分段摘要失败，降级到整体硬截断")
            return self.truncate_by_token(text, max_tokens)

        return "\n".join(summaries)

    def _split_by_tokens(self, text: str, max_tokens_per_segment: int) -> list[str]:
        """按 token 数将文本切分为多段，每段不超过 max_tokens_per_segment。"""
        tokens = self.tokenizer.encode(text)
        segments: list[str] = []
        for i in range(0, len(tokens), max_tokens_per_segment):
            segment_tokens = tokens[i : i + max_tokens_per_segment]
            segments.append(self.tokenizer.decode(segment_tokens))
        return segments
