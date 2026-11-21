# app-server/src/com/damon/ming/ai/rag/spliter/__init__.py

from src.com.damon.ming.ai.rag.spliter.spliter import (
    BaseDocumentSplitter,
    StructuredDocumentSplitter,
)


def create_splitters(*, tokenizer, max_input_tokens: int | None = None):
    """加载 splitter 策略，并应用 embedding 提供的输入上限。"""
    from src.com.damon.ming.ai.rag.spliter.manager import SplitterManager

    manager = SplitterManager()
    manager.initialize(tokenizer, max_input_tokens)
    return manager


__all__ = [
    "BaseDocumentSplitter",
    "StructuredDocumentSplitter",
    "create_splitters",
]
