# app-server/src/com/damon/ming/ai/rag/summary/summary_service.py
"""
摘要服务 —— 封装所有 LLM 摘要压缩能力，与 reconstruction 解耦。

职责：
  - 单文本摘要（含分段和容错）
  - rerank 前压缩（操作副本，不碰原数据）
  - 不持有线程池，纯 asyncio 并发

取消策略：
  - 不感知取消——由上层 RagChoreographer 通过 asyncio.CancelledError 统一处理
  - compress_nodes / run_summary 中的 await 点被 CancelledError 自然中断
  - 中断时直接抛弃所有中间结果（副本、压缩文本等），不做任何保存/恢复
"""

import asyncio
import copy

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.inference.inference_gateway import InferenceGateway
from src.com.damon.ming.ai.rag.config.summary.summary_config_loader import (
    SummaryConfig,
)
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.log import pin

logger = pin("SummaryService")


SUMMARY_PROMPT_TEMPLATE = """你是文本摘要助手，精简下面文档内容，保留全部关键数据、结论、条款，不要冗余描述。
摘要控制在{max_tokens}token以内，直接输出摘要，不要多余解释：
文档内容：
{content}
"""


class SummaryService:
    """摘要压缩服务，纯技术模块，不含业务逻辑。"""

    def __init__(
        self,
        tokenizer: BaseTokenizer,
        inference: InferenceGateway,
        config: SummaryConfig,
    ):
        self.tokenizer = tokenizer
        self.inference = inference
        self.config = config

    # ── 公开接口 ──────────────────────────────────────────────────────

    async def _guarded_summary(self, text: str, max_tokens: int) -> str:
        """调用摘要推理，并发控制由 Gateway 管理。"""
        return await self._run_single_summary(text, max_tokens)

    async def run_summary(self, text: str, max_tokens: int) -> str:
        """单文本摘要压缩。超长自动分段，失败降级硬截断。"""
        num_ctx = self.inference.get_summary().context_window()
        input_limit = int(num_ctx * self.config.input_max_ratio)
        text_tokens = self.tokenizer.count_tokens(text)

        if text_tokens > input_limit:
            return await self._run_segmented_summary(text, max_tokens, input_limit)

        return await self._guarded_summary(text, max_tokens)

    async def compress_nodes(
        self, nodes: list[TextNode], max_tokens: int
    ) -> list[TextNode]:
        """批量压缩超长节点（返回新节点，不修改输入）。

        对超过 max_tokens 的节点并发调用 run_summary 压缩。
        返回深拷贝节点，避免并发请求间写共享 TextNode。

        取消安全：取消时显式清理所有未完成任务，原始 nodes 不被修改。
        """
        # 收集需要压缩的节点索引，避免迭代过程中 nodes 被修改
        compress_indices: list[int] = []
        for idx, node in enumerate(nodes):
            if self.tokenizer.count_tokens(node.text) > max_tokens:
                compress_indices.append(idx)

        if not compress_indices:
            return nodes

        # 并发执行所有压缩任务
        tasks = [
            asyncio.create_task(
                self._guarded_summary(text=nodes[idx].text, max_tokens=max_tokens)
            )
            for idx in compress_indices
        ]

        # 收集结果，取消时显式清理孤儿 task
        compressed_texts: list[str] = []
        try:
            compressed_texts = await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            # CancelledError 从 gather 直接传播，tasks 已被取消，无需二次 gather
            for t in tasks:
                t.cancel()
            raise
        except Exception:
            # 非取消异常（如 LLM 调用失败）：清理已创建的任务
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        # 所有任务成功：一次性替换节点（原子性，避免部分修改）
        # 先浅拷贝输入列表，再在新列表上替换，保持输入列表不被修改。
        result_nodes = list(nodes)
        for i, idx in enumerate(compress_indices):
            text = compressed_texts[i]
            # LLM 输出可能略微超出 max_tokens，截断兜底保证不超限
            if self.tokenizer.count_tokens(text) > max_tokens:
                logger.warning(
                    "LLM摘要后仍超限 | 摘要tokens=%d | max=%d | 截断兜底",
                    self.tokenizer.count_tokens(text),
                    max_tokens,
                )
                text = self.truncate_by_token(text, max_tokens)
            new_node = copy.deepcopy(nodes[idx])
            new_node.text = text
            result_nodes[idx] = new_node
        return result_nodes

    # ── 取消说明 ────────────────────────────────────────────────────────
    # 取消由上层 RagChoreographer 通过 asyncio.CancelledError 统一处理，
    # compress_nodes / run_summary 中的 await 点被自然中断，
    # 压缩结果直接丢弃，无需任何清理或恢复操作。

    def truncate_by_token(self, text: str, max_tokens: int) -> str:
        """按 token 数硬截断文本。"""
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.tokenizer.decode(tokens[:max_tokens])

    # ── 私有：摘要实现 ────────────────────────────────────────────────

    async def _run_single_summary(self, text: str, max_tokens: int) -> str:
        """单段摘要，带容错降级。"""
        prompt = SUMMARY_PROMPT_TEMPLATE.replace(
            "{max_tokens}", str(max_tokens), 1
        ).replace("{content}", text, 1)
        # max_tokens 为通用输出上限键，由推理层按引擎翻译（vLLM 直用 / Ollama → num_predict）。
        # 目标值覆盖角色默认值，保证摘要长度受调用方控制。
        try:
            return await self.inference.get_summary().generate(
                messages=[{"role": "user", "content": prompt}],
                options={"max_tokens": max_tokens},
            )
        except asyncio.CancelledError:
            logger.warning("_run_single_summary | 摘要生成被取消")
            raise
        except Exception as e:
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
            self._guarded_summary(segment, per_segment_max) for segment in segments
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        summaries: list[str] = []
        for i, r in enumerate(results):
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
