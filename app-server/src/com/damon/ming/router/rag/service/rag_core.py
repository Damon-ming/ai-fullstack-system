# app-server/src/com/damon/ming/router/rag/service/rag_core.py
"""
推理核心 —— 同步 / 流式共用的 Phase 2 全流程。

从 rag_router 抽出：两个端点原本各自重复「RAG 检索 → 拼 messages →
进推理信号量 → 逐 token 拉取」整段，连同 system prompt 纯净性（防模板注入）
与超时预算口径的约束一起收敛到一处。
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing

from src.com.damon.ming.ai.inference.base_inference import StreamToken
from src.com.damon.ming.i18n import get_locale
from src.com.damon.ming.i18n.locale_negotiator import get_default_locale
from src.com.damon.ming.log import pin

logger = pin("chat.core")


def _resolve_locale_text(rag_locales: dict, locale: str):
    """按请求 locale 取文本配置，缺省回退 i18n 配置的 default_locale。"""
    return rag_locales.get(locale) or rag_locales[get_default_locale()]


async def _build_prompt_messages(app_state, query: str) -> list[dict[str, str]]:
    """RAG 检索参考资料并构造标准 messages 数组。

    system prompt 保持纯净（只含指令），用户数据（参考资料 + 问题）全部放在
    user message 中，避免 ref_content 中的模板占位符或恶意内容污染 system prompt。
    消息标签从 YAML 配置读取，与 system prompt 同文件管理。
    """

    # RAG 上下文处理在推理信号量外执行，由 rag_sem 做反压。
    async with app_state.ai.rag.rag_sem:
        logger.debug("开始执行 RAG 检索")
        ref_content = await app_state.ai.rag.choreographer.build_rag_context(
            query,
        )

    chat_cfg = _resolve_locale_text(app_state.ai.rag.locales, get_locale())

    prompt_messages = [
        {"role": "system", "content": chat_cfg.system_prompt},
        {
            "role": "user",
            "content": f"{chat_cfg.ref_label}\n{ref_content}\n\n{chat_cfg.query_label}{query}",
        },
    ]
    logger.debug("prompt_messages:\n%s", prompt_messages)
    return prompt_messages


async def generate_answer(
    app_state,
    query: str,
    reason: bool,
) -> AsyncGenerator[StreamToken, None]:
    """Phase 2 全流程：RAG 检索 → prompt 组装 → 推理，逐 token 产出。

    超时预算覆盖检索、上下文构造、主推理及并发槽等待，不含前置护栏检测；
    仅推理段进入推理信号量，释放 RAG 等待期间的并发槽。
    CancelledError 不加内层捕获，直接穿透到外层统一处理，
    确保 infer_service 内部 finally 能正确关闭推理流。
    """
    async with asyncio.timeout(app_state.ai.rag.execution_timeout_seconds):
        prompt_messages = await _build_prompt_messages(app_state, query)
        async with aclosing(
            app_state.ai.inference.gateway.get_inference().stream(
                messages=prompt_messages, reason=reason
            )
        ) as stream:
            async for token in stream:
                yield token
