# app-server/src/com/damon/ming/ai/registry/rerank_registry.py
from src.com.damon.ming.ai.rerank.cross_encoder_reranker import CrossEncoderReranker
from src.com.damon.ming.ai.rerank.factory import RerankerFactory
from src.com.damon.ming.log import pin

logger = pin("RerankRegistry")


def register_all_rerankers():
    """项目启动统一注册所有重排器实现"""
    RerankerFactory.register("cross_encoder", CrossEncoderReranker)
    logger.info(f"[Registry] 已注册重排器: {RerankerFactory._registry.keys()}")
