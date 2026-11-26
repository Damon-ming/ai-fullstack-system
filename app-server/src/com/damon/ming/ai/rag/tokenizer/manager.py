# app-server/src/com/damon/ming/ai/rag/tokenizer/manager.py
"""RAG 分词器的初始化和访问入口。"""

from pathlib import Path
from typing import cast

from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import (
    BaseTokenizer,
    BaseWordTokenizer,
)
from src.com.damon.ming.ai.rag.tokenizer.config import (
    TokenizerConfig,
    TokenizerRoleConfig,
)
from src.com.damon.ming.ai.rag.tokenizer.embedding_tokenizer import EmbeddingTokenizer
from src.com.damon.ming.ai.rag.tokenizer.params import (
    JiebaTokenizerParams,
    TiktokenTokenizerParams,
)


class RagTokenizers:
    def __init__(self) -> None:
        self._items: dict[str, object] | None = None
        self._embedding_tokenizer: BaseTokenizer | None = None

    def initialize(self, config: dict[str, object], embedding_tokenizer=None) -> None:
        if self._items is not None:
            raise RuntimeError("RAG 分词器已经初始化")
        parsed_config = TokenizerConfig.from_mapping(config)
        from src.com.damon.ming.ai.rag.tokenizer import list_engines, resolve_tokenizer
        from src.com.damon.ming.log import pin

        engines = list_engines()
        if engines:
            pin("RagTokenizers").info("[Registry] 可用分词器引擎: %s", engines)
        else:
            pin("RagTokenizers").warning("[Registry] 未注册任何分词器引擎")
        items: dict[str, object] = {}
        for name, spec in parsed_config.roles.items():
            params = self._build_params(name, spec)
            items[name] = resolve_tokenizer(spec.tokenizer_engine)(params)
        self._items = items
        if embedding_tokenizer is not None:
            self._embedding_tokenizer = EmbeddingTokenizer(embedding_tokenizer)

    @staticmethod
    def _build_params(name: str, spec: TokenizerRoleConfig):
        if spec.tokenizer_engine == "tiktoken":
            return TiktokenTokenizerParams(encoding_name=spec.params["encoding_name"])
        if spec.tokenizer_engine == "jieba":
            return JiebaTokenizerParams(
                user_dict_paths=RagTokenizers._discover_jieba_dict_paths(
                    spec.params, name
                )
            )
        raise ValueError(f"未知分词器引擎: {spec.tokenizer_engine}")

    @staticmethod
    def _discover_jieba_dict_paths(params: dict, name: str) -> tuple[str, ...]:
        dicts_dir_name = params.get("dicts_dir")
        if dicts_dir_name is None or dicts_dir_name == "":
            return ()
        dicts_dir_name = dicts_dir_name.strip()
        if not dicts_dir_name:
            return ()
        dicts_dir = (Path(__file__).resolve().parent / dicts_dir_name).resolve()
        if not dicts_dir.is_dir():
            raise FileNotFoundError(f"分词器 '{name}' 的词典目录不存在: {dicts_dir}")
        return tuple(
            str(path.resolve())
            for path in sorted(dicts_dir.glob("*.txt"))
            if path.is_file()
        )

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

    def get_embedding_tokenizer(self) -> BaseTokenizer | None:
        if self._items is None:
            raise RuntimeError("RAG 分词器尚未初始化")
        return self._embedding_tokenizer
