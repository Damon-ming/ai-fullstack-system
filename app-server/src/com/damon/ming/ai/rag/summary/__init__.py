"""RAG 文本摘要能力。"""

from src.com.damon.ming.ai.inference.inference_gateway import InferenceGateway
from src.com.damon.ming.ai.rag.config.summary.summary_config_loader import (
    SummaryConfigLoader,
)
from src.com.damon.ming.ai.rag.summary.summary_service import SummaryService
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer


def create_summary_service(
    tokenizer: BaseTokenizer,
    inference: InferenceGateway,
) -> SummaryService:
    """加载摘要配置并创建摘要服务。"""
    return SummaryService(
        tokenizer=tokenizer,
        inference=inference,
        config=SummaryConfigLoader().load(),
    )


__all__ = ["SummaryService", "create_summary_service"]
