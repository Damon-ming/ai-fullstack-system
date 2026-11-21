# app-server/src/com/damon/ming/ai/rag/spliter/manager.py
"""分割器的初始化和访问入口。"""

from src.com.damon.ming.ai.rag.spliter.config.splitter_config_loader import (
    SplitterConfigLoader,
)
from src.com.damon.ming.ai.rag.spliter.spliter import MarkdownDocumentSplitter
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer


class SplitterManager:
    """加载分块配置并创建分割器。"""

    def __init__(self) -> None:
        self._markdown: MarkdownDocumentSplitter | None = None

    def initialize(self, tokenizer: BaseTokenizer) -> None:
        if self._markdown is not None:
            raise RuntimeError("RAG 分割器已经初始化")
        config = SplitterConfigLoader().load()
        self._markdown = MarkdownDocumentSplitter(
            tokenizer=tokenizer,
            max_chunk_token_size=config.max_chunk_token_size,
            chunk_overlap=config.chunk_overlap,
        )

    def get_markdown(self) -> MarkdownDocumentSplitter:
        if self._markdown is None:
            raise RuntimeError("RAG 分割器尚未初始化")
        return self._markdown
