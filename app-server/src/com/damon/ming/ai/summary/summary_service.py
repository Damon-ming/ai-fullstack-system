# app-server/src/com/damon/ming/ai/summary/summary_service.py
"""
摘要服务 —— 封装所有 LLM 摘要压缩能力，与 reconstruction 解耦。

职责：
  - 单文本摘要（含分段和容错）
  - rerank 前压缩（操作副本，不碰原数据）
  - 不持有线程池，纯 asyncio 并发

取消策略：
  - 不感知取消——由上层 RAGContainer 通过 asyncio.CancelledError 统一处理
  - compress_nodes / run_summary 中的 await 点被 CancelledError 自然中断
  - 中断时直接抛弃所有中间结果（副本、压缩文本等），不做任何保存/恢复
"""

import asyncio

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.inference.base_inference import BaseInferenceService
from src.com.damon.ming.ai.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.log import pin

logger = pin("SummaryService")


SUMMARY_PROMPT_TEMPLATE = """你是文本摘要助手，精简下面文档内容，保留全部关键数据、结论、条款，不要冗余描述。
摘要控制在{max_tokens}token以内，直接输出摘要，不要多余解释：
文档内容：
{content}
"""

# 摘要输入占模型上下文窗口的最大比例，留出空间给 prompt 模板和输出
SUMMARY_INPUT_MAX_RATIO = 0.6


class SummaryService:
    """摘要压缩服务，纯技术模块，不含业务逻辑。"""

    def __init__(
        self,
        tokenizer: BaseTokenizer,
        inference: BaseInferenceService | None = None,
        summary_model: str = "",
        summary_options: dict | None = None,
    ):
        self.tokenizer = tokenizer
        self.inference = inference
        self.summary_model = summary_model
        self.summary_options = summary_options or {}

    # ── 公开接口 ──────────────────────────────────────────────────────

    async def run_summary(self, text: str, max_tokens: int) -> str:
        """单文本摘要压缩。超长自动分段，失败降级硬截断。"""
        num_ctx = self.summary_options.get("num_ctx", 4096)
        input_limit = int(num_ctx * SUMMARY_INPUT_MAX_RATIO)
        text_tokens = self.tokenizer.count_tokens(text)

        if text_tokens > input_limit:
            return await self._run_segmented_summary(text, max_tokens, input_limit)

        return await self._run_single_summary(text, max_tokens)

    async def compress_nodes(
        self, nodes: list[TextNode], max_tokens: int
    ) -> list[TextNode]:
        """批量压缩超长节点（原地修改）。

        对超过 max_tokens 的节点并发调用 run_summary 压缩。
        调用方传入原节点或克隆副本均可，本方法不做区分。
        取消时由 CancelledError 自然传播，结果直接丢弃。
        """
        tasks: list[tuple[TextNode, asyncio.Task]] = []
        for node in nodes:
            token_cnt = self.tokenizer.count_tokens(node.text)
            if token_cnt > max_tokens:
                logger.info(f"节点压缩 | tokens={token_cnt} | max_tokens={max_tokens}")
                tasks.append(
                    (node, asyncio.create_task(
                        self.run_summary(text=node.text, max_tokens=max_tokens)
                    ))
                )

        for node, task in tasks:
            node.text = await task  # CancelledError 传播时自动丢弃
        return nodes

    # ── 取消说明 ────────────────────────────────────────────────────────
    # 取消由上层 RAGContainer 通过 asyncio.CancelledError 统一处理，
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
        prompt = SUMMARY_PROMPT_TEMPLATE.format(max_tokens=max_tokens, content=text)
        opts = {"temperature": 0.1, "num_predict": max_tokens}
        opts.update(self.summary_options)
        try:
            return await self.inference.text_generation(
                model_name=self.summary_model,
                messages=[{"role": "user", "content": prompt}],
                options=opts,
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
            self._run_single_summary(segment, per_segment_max) for segment in segments
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
