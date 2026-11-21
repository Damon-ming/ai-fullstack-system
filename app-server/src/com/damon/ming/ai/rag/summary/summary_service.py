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
import re
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
        """二分法按 token 截断文本: 按 token 上限截取原文前缀，避免 token decode 切断 UTF-8 字符。"""
        if self.tokenizer.count_tokens(text) <= max_tokens:
            return text

        start, end = 0, len(text)
        best_end = 0
        while start <= end:
            middle = (start + end) // 2
            if self.tokenizer.count_tokens(text[:middle]) <= max_tokens:
                best_end = middle
                start = middle + 1
            else:
                end = middle - 1

        # 极小 token 上限可能连一个完整 Unicode 字符都容不下，优先保留字符完整性。
        if best_end == 0 and text:
            return text[0]
        return text[:best_end]

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

    async def _run_single_summary(
        self, text: str, max_tokens: int, *, fallback_on_error: bool = True
    ) -> str:
        """单段摘要，带容错降级。"""
        messages = self._build_messages(text, max_tokens)
        # max_tokens 为通用输出上限键，由推理层按引擎翻译（vLLM 直用 / Ollama → num_predict）。
        # 目标值覆盖角色默认值，保证摘要长度受调用方控制。
        try:
            summary = await self.summary_inference.generate(
                messages=messages,
                options={"max_tokens": max_tokens},
            )
            return self.truncate_by_token(summary, max_tokens)
        except asyncio.CancelledError:
            logger.warning("_run_single_summary | 摘要生成被取消")
            raise
        except Exception as e:
            if isinstance(e, ContextWindowExceededError):
                if fallback_on_error:
                    logger.warning("摘要后端返回上下文超限，直接硬截断")
                else:
                    logger.warning("摘要后端返回上下文超限，交由分段结果收集器兜底")
            else:
                if fallback_on_error:
                    logger.warning(f"摘要生成失败，降级到硬截断 | error={e}")
                else:
                    logger.warning(f"摘要生成失败，交由分段结果收集器兜底 | error={e}")
            if not fallback_on_error:
                raise
            return self.truncate_by_token(text, max_tokens)

    async def _run_segmented_summary(
        self, text: str, max_tokens: int, segment_size: int
    ) -> str:
        """将超长文本分段摘要，再合并结果。"""
        segments = self._split_text_preserving_boundaries(text, segment_size)
        logger.info(
            f"文本超长({self.tokenizer.count_tokens(text)}tokens)，"
            f"分{len(segments)}段摘要 | segment_size={segment_size}"
        )

        separator = "\n"
        separator_tokens = self.tokenizer.count_tokens(
            separator * max(len(segments) - 1, 0)
        )
        content_budget = max(max_tokens - separator_tokens, 1)
        output_budgets = self._allocate_output_budgets(segments, content_budget)
        summary_tasks = [
            asyncio.create_task(
                self._run_single_summary(
                    segment, output_budget, fallback_on_error=False
                )
            )
            for segment, output_budget in zip(segments, output_budgets)
        ]
        try:
            results = await asyncio.gather(*summary_tasks, return_exceptions=True)
        except (asyncio.CancelledError, Exception) as e:
            for task in summary_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*summary_tasks, return_exceptions=True)
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.warning("分段摘要任务异常，整批降级到硬截断 | error=%s", e)
            return self.truncate_by_token(text, max_tokens)

        summaries: list[str] = []
        for index, (result, segment, output_budget) in enumerate(
            zip(results, segments, output_budgets), start=1
        ):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, Exception):
                logger.warning(
                    "第%d/%d段摘要失败，使用该段原文截断兜底 | error=%s",
                    index,
                    len(segments),
                    result,
                )
                summaries.append(self.truncate_by_token(segment, output_budget))
                continue
            summaries.append(self.truncate_by_token(result, output_budget))

        if not summaries:
            logger.warning("全部分段摘要失败，降级到整体硬截断")
            return self.truncate_by_token(text, max_tokens)

        combined_summary = separator.join(summaries)

        if self.tokenizer.count_tokens(combined_summary) > max_tokens:
            logger.warning(
                "分段摘要合并后仍超过目标，执行一次摘要收敛 | 摘要tokens=%d | max=%d",
                self.tokenizer.count_tokens(combined_summary),
                max_tokens,
            )
            return await self.run_summary(combined_summary, max_tokens)

        return combined_summary

    def _allocate_output_budgets(
        self, segments: list[str], max_tokens: int
    ) -> list[int]:
        """按片段输入长度分配输出额度，保证片段数不超过预算时额度总和相等于总预算。"""
        segment_count = len(segments)
        if segment_count == 0:
            return []
        if segment_count > max_tokens:
            # 每段至少需要一个输出 token；合并后由一次收敛摘要压回总预算。
            return [1] * segment_count

        weights = [max(self.tokenizer.count_tokens(segment), 1) for segment in segments]
        remaining = max_tokens - segment_count
        total_weight = sum(weights)
        shares = [remaining * weight / total_weight for weight in weights]
        budgets = [1 + floor(share) for share in shares]
        leftover = max_tokens - sum(budgets)
        order = sorted(
            range(segment_count),
            key=lambda index: shares[index] - floor(shares[index]),
            reverse=True,
        )
        for index in order[:leftover]:
            budgets[index] += 1
        return budgets

    def _split_text_preserving_boundaries(
        self, text: str, max_tokens_per_segment: int
    ) -> list[str]:
        """优先按章节、段落和句子拆分，始终从原文切片以保留字符。"""
        if max_tokens_per_segment <= 0:
            raise ValueError("分段 token 上限必须大于 0")
        if self.tokenizer.count_tokens(text) <= max_tokens_per_segment:
            return [text]

        segments: list[str] = []
        current = ""
        for section in self._split_sections(text):
            if self.tokenizer.count_tokens(section) <= max_tokens_per_segment:
                if (
                    current
                    and self.tokenizer.count_tokens(current + section)
                    > max_tokens_per_segment
                ):
                    segments.append(current)
                    current = ""
                current += section
                continue

            if current:
                segments.append(current)
                current = ""

            heading_match = re.match(r"^(【[^\r\n]+】(?:\r?\n)?)", section)
            heading = heading_match.group(1) if heading_match else ""
            if (
                heading
                and self.tokenizer.count_tokens(heading) < max_tokens_per_segment
            ):
                body_segments = self._split_natural_text(
                    section[len(heading) :],
                    max_tokens_per_segment - self.tokenizer.count_tokens(heading),
                )
                segments.extend(heading + body for body in body_segments)
            else:
                segments.extend(
                    self._split_natural_text(section, max_tokens_per_segment)
                )

        if current:
            segments.append(current)
        return segments

    @staticmethod
    def _split_sections(text: str) -> list[str]:
        """按重构阶段使用的章节分隔符切分，并将分隔符保留在前一节。"""
        sections: list[str] = []
        start = 0
        for match in re.finditer(r"\n---\n", text):
            sections.append(text[start : match.end()])
            start = match.end()
        if start < len(text):
            sections.append(text[start:])
        return sections or [text]

    def _split_natural_text(self, text: str, max_tokens: int) -> list[str]:
        """按换行和句末标点拆分，超长句再按词和 Unicode 字符细分。"""
        boundaries = re.finditer(
            r"(?:\r?\n)+|[。！？!?]+(?:[”’」』】）》\"']*)|"
            r"[.]+(?:[”’」』】）》\"']*)(?=\s|$)",
            text,
        )
        units: list[str] = []
        start = 0
        for boundary in boundaries:
            end = boundary.end()
            if end > start:
                units.append(text[start:end])
                start = end
        if start < len(text):
            units.append(text[start:])
        return self._pack_units(units or [text], max_tokens)

    def _pack_units(self, units: list[str], max_tokens: int) -> list[str]:
        segments: list[str] = []
        current = ""
        for unit in units:
            if self.tokenizer.count_tokens(unit) > max_tokens:
                if current:
                    segments.append(current)
                    current = ""
                segments.extend(self._split_long_unit(unit, max_tokens))
            elif current and self.tokenizer.count_tokens(current + unit) > max_tokens:
                segments.append(current)
                current = unit
            else:
                current += unit
        if current:
            segments.append(current)
        return segments

    def _split_long_unit(self, text: str, max_tokens: int) -> list[str]:
        """先按空白边界切分，单个超长词再按 Unicode 字符安全切分。"""
        pieces = re.findall(r"\s+|\S+", text)
        if not pieces:
            return [text]

        segments: list[str] = []
        current = ""
        for piece in pieces:
            if self.tokenizer.count_tokens(piece) > max_tokens:
                if current:
                    segments.append(current)
                    current = ""
                segments.extend(self._split_by_characters(piece, max_tokens))
            elif current and self.tokenizer.count_tokens(current + piece) > max_tokens:
                segments.append(current)
                current = piece
            else:
                current += piece
        if current:
            segments.append(current)
        return segments

    def _split_by_characters(self, text: str, max_tokens: int) -> list[str]:
        """在原始字符串上找 token 预算内的 Unicode 字符切片，不做 token decode。"""
        segments: list[str] = []
        start = 0
        while start < len(text):
            low, high = start + 1, len(text)
            best_end = start
            while low <= high:
                middle = (low + high) // 2
                if self.tokenizer.count_tokens(text[start:middle]) <= max_tokens:
                    best_end = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if best_end == start:
                # 单个字符也可能超过极小预算；保留字符完整性并让后端错误走既有兜底。
                best_end = start + 1
            segments.append(text[start:best_end])
            start = best_end
        return segments
