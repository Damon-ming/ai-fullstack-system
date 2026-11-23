# app-server/src/com/damon/ming/ai/rag/spliter/manager.py
"""分割器的初始化和访问入口。"""

from src.com.damon.ming.ai.rag.spliter.config.splitter_config_loader import (
    SplitterConfigLoader,
)
from src.com.damon.ming.ai.rag.spliter.spliter import StructuredDocumentSplitter
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer


class SplitterManager:
    """加载切分策略，并结合 embedding 输入上限创建分割器。"""

    def __init__(self) -> None:
        self._structured: StructuredDocumentSplitter | None = None

    def initialize(
        self,
        tokenizer: BaseTokenizer,
        max_input_tokens: int | None = None,
    ) -> None:
        if self._structured is not None:
            raise RuntimeError("RAG 分割器已经初始化")
        config = SplitterConfigLoader().load()
        chunk_size = config.max_chunk_token_size
        if max_input_tokens is not None:
            chunk_size = min(chunk_size, max_input_tokens)
        overlap = min(config.chunk_overlap, chunk_size - 1)
        self._structured = StructuredDocumentSplitter(
            tokenizer=tokenizer,
            max_chunk_token_size=chunk_size,
            chunk_overlap=overlap,
            max_grouped_chunks_per_section=config.max_grouped_chunks_per_section,
            max_headed_chunks_per_section=config.max_headed_chunks_per_section,
        )

    def get_structured(self) -> StructuredDocumentSplitter:
        if self._structured is None:
            raise RuntimeError("RAG 分割器尚未初始化")
        return self._structured
