# app-server/src/com/damon/ming/ai/registry/embedding_registry.py
"""
Embedding 启动校验 —— 确认引擎注册表已就绪。

实际注册由各实现类通过 @register_engine 装饰器在 import 时自动完成。
本模块仅做启动时校验，确保引擎可用。
"""
from src.com.damon.ming.ai.embedding import list_engines
from src.com.damon.ming.log import pin

logger = pin("EmbeddingRegistry")


def register_all_embeddings():
    """项目启动时校验 embedding 注册表。"""
    engines = list_engines()
    if not engines:
        logger.warning("[Registry] 未注册任何 embedding 引擎")
    else:
        logger.info(f"[Registry] 可用 embedding 引擎: {engines}")
