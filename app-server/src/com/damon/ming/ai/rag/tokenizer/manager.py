# app-server/src/com/damon/ming/ai/rag/tokenizer/manager.py
"""RAG 分词器的初始化和访问入口。"""

from typing import cast

from src.com.damon.ming.ai.rag.tokenizer.config.tokenizer_config_loader import (
    TokenizerConfigLoader,
)
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import (
    BaseTokenizer,
    BaseWordTokenizer,
)


class RagTokenizers:
    def __init__(self) -> None:
        self._items: dict[str, object] | None = None

    def initialize(self) -> None:
        if self._items is not None:
            raise RuntimeError("RAG 分词器已经初始化")
        from src.com.damon.ming.ai.rag.tokenizer import list_engines
        from src.com.damon.ming.log import pin

        engines = list_engines()
        if engines:
            pin("TokenizerRegistry").info("[Registry] 可用分词器引擎: %s", engines)
        else:
            pin("TokenizerRegistry").warning("[Registry] 未注册任何分词器引擎")
        self._items = TokenizerConfigLoader().load_all()

    def _get(self, name: str) -> object:
        if self._items is None:
            raise RuntimeError("RAG 分词器尚未初始化")
        try:
            return self._items[name]
        except KeyError as exc:
            raise ValueError(f"缺少 RAG 分词器配置: {name}") from exc

    def get_llm_tokenizer(self) -> BaseTokenizer:
        return cast(BaseTokenizer, self._get("llm_counter"))

    def get_bm25_tokenizer(self) -> BaseWordTokenizer:
        return cast(BaseWordTokenizer, self._get("bm25_searcher"))
