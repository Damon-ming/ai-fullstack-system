# app-server/src/com/damon/ming/ai/rag/spliter/__init__.py

from src.com.damon.ming.ai.rag.spliter.spliter import (
    BaseDocumentSplitter,
    StructuredDocumentSplitter,
)
from src.com.damon.ming.app.config.ai.rag.rag_runtime_config_loader import (
    SplitterRuntimeConfig,
)


def create_splitters(
    *,
    tokenizer,
    max_chunk_token_size: int,
    max_input_tokens: int,
    config: SplitterRuntimeConfig,
):
    """使用注入的 splitter 策略，并应用 embedding 输入上限。"""
    from src.com.damon.ming.ai.rag.spliter.manager import SplitterManager

    manager = SplitterManager()
    manager.initialize(tokenizer, max_chunk_token_size, max_input_tokens, config)
    return manager


__all__ = [
    "BaseDocumentSplitter",
    "StructuredDocumentSplitter",
    "create_splitters",
]
