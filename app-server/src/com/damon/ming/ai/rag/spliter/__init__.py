# app-server/src/com/damon/ming/ai/rag/spliter/__init__.py

from src.com.damon.ming.ai.rag.spliter.spliter import (
    BaseDocumentSplitter,
    MarkdownDocumentSplitter,
)


def create_splitters(tokenizer):
    """加载配置并创建分割器。"""
    from src.com.damon.ming.ai.rag.spliter.manager import SplitterManager

    manager = SplitterManager()
    manager.initialize(tokenizer)
    return manager


__all__ = [
    "BaseDocumentSplitter",
    "MarkdownDocumentSplitter",
    "create_splitters",
]
