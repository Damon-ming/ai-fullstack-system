# app-server/src/com/damon/ming/ai/rag/summary/__init__.py
"""RAG 文本摘要能力。"""

from src.com.damon.ming.ai.inference.inference_gateway import RoleInference
from src.com.damon.ming.ai.rag.summary.config import SummaryConfig
from src.com.damon.ming.ai.rag.summary.summary_service import SummaryService
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer


def create_summary_service(
    tokenizer: BaseTokenizer,
    summary_inference: RoleInference,
    config: dict[str, object],
) -> SummaryService:
    """使用注入的摘要配置创建摘要服务。"""
    return SummaryService(
        tokenizer=tokenizer,
        summary_inference=summary_inference,
        config=SummaryConfig.from_mapping(config),
    )


__all__ = ["SummaryConfig", "SummaryService", "create_summary_service"]
