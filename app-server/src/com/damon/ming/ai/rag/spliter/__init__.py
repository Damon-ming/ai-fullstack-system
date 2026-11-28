# app-server/src/com/damon/ming/ai/rag/spliter/__init__.py

from src.com.damon.ming.ai.rag.spliter.config import SplitterConfig
from src.com.damon.ming.ai.rag.spliter.spliter import (
    BaseDocumentSplitter,
    StructuredDocumentSplitter,
)


def create_splitters(
    *,
    tokenizer,
    max_document_tokens: int,
    config: dict[str, object],
):
    """使用注入的 splitter 策略，并应用 embedding 单块正文上限。"""
    from src.com.damon.ming.ai.rag.spliter.manager import SplitterManager

    manager = SplitterManager()
    manager.initialize(tokenizer, max_document_tokens, config)
    return manager


__all__ = [
    "BaseDocumentSplitter",
    "SplitterConfig",
    "StructuredDocumentSplitter",
    "create_splitters",
]
