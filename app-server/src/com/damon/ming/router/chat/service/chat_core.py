# app-server/src/com/damon/ming/router/chat/service/chat_core.py
"""
推理核心 —— 同步 / 流式共用的 Phase 2 全流程。

从 chat_router 抽出：两个端点原本各自重复「RAG 检索 → 拼 messages →
进推理信号量 → 逐 token 拉取」整段，连同 system prompt 纯净性（防模板注入）
与超时预算口径的约束一起收敛到一处。
"""

import asyncio
from collections.abc import AsyncGenerator

from src.com.damon.ming.ai.inference.base_inference import StreamToken
from src.com.damon.ming.i18n import get_locale
from src.com.damon.ming.i18n.locale_negotiator import get_default_locale
from src.com.damon.ming.log import pin
from src.com.damon.ming.thread import CancellationToken

logger = pin("chat.core")

# RAG 检索上下文 token 上限（与 vLLM max-model-len 对齐）
# 约束：system(~200) + context_budget + query(~50) + max_tokens(1024) ≤ 2048
# 跑通模式：budget=512 → 总占用 ~1826 ≤ 2048
# 完整模式：换大模型后同步调高（max-model-len 4096 → budget 可设 2048）
MAX_CONTEXT_TOKEN_BUDGET = 512


def _resolve_locale_text(chat_locales: dict, locale: str):
    """按请求 locale 取文本配置，缺省回退 i18n 配置的 default_locale。"""
    return chat_locales.get(locale) or chat_locales[get_default_locale()]


async def _build_prompt_messages(
    app_state, query: str, cancellation_token: CancellationToken | None = None
) -> list[dict[str, str]]:
    """RAG 检索参考资料并构造标准 messages 数组。

    system prompt 保持纯净（只含指令），用户数据（参考资料 + 问题）全部放在
    user message 中，避免 ref_content 中的模板占位符或恶意内容污染 system prompt。
    消息标签从 YAML 配置读取，与 system prompt 同文件管理。
    """
    chat_cfg = _resolve_locale_text(app_state.chat.locales, get_locale())

    # RAG 检索在推理信号量外执行（自身有线程池保护 + rag_sem 反压）
    async with app_state.chat.rag_sem:
        logger.debug("开始执行 RAG 检索")
        ref_content = await app_state.ai.rag_app.query_rag(
            query,
            max_context_tokens=MAX_CONTEXT_TOKEN_BUDGET,
            cancellation_token=cancellation_token,
        )

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
    cancellation_token: CancellationToken | None = None,
) -> AsyncGenerator[StreamToken, None]:
    """Phase 2 全流程：RAG 检索 → prompt 组装 → 推理，逐 token 产出。

    超时预算覆盖 RAG + 推理整段（两端点共享同一口径）；
    仅推理段进入推理信号量，释放 RAG 等待期间的并发槽。
    CancelledError 不加内层捕获，直接穿透到外层统一处理，
    确保 infer_service 内部 finally 能正确关闭推理流。
    """
    async with asyncio.timeout(app_state.chat.timeout):
        prompt_messages = await _build_prompt_messages(
            app_state, query, cancellation_token
        )
        async with app_state.chat.sem:
            async for token in app_state.ai.infer_service.stream_generate(
                model_name=app_state.ai.model_name,
                messages=prompt_messages,
                reason=reason,
                options=dict(app_state.ai.options),
            ):
                yield token
