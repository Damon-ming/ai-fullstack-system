# app-server/src/com/damon/ming/ai/rag/summary/__init__.py
"""RAG 文本摘要能力。"""

from src.com.damon.ming.ai.inference.inference_gateway import RoleInference
from src.com.damon.ming.ai.rag.summary.summary_service import SummaryService
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.app.config.ai.rag.rag_runtime_config_loader import (
    SummaryRuntimeConfig,
)


def create_summary_service(
    tokenizer: BaseTokenizer,
    summary_inference: RoleInference,
    config: SummaryRuntimeConfig,
) -> SummaryService:
    """使用注入的摘要配置创建摘要服务。"""
    return SummaryService(
        tokenizer=tokenizer,
        summary_inference=summary_inference,
        config=config,
    )


__all__ = ["SummaryService", "create_summary_service"]
