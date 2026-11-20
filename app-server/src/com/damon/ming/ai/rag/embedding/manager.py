"""RAG embedding 模型的初始化和访问入口。"""

from src.com.damon.ming.ai.rag.config.embedding.embedding_config_loader import (
    EmbeddingConfigLoader,
)
from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)


class RagEmbedders:
    def __init__(self) -> None:
        self._items: dict[str, BaseEmbeddingService] | None = None

    def initialize(self) -> None:
        if self._items is not None:
            raise RuntimeError("RAG embedding已经初始化")
        from src.com.damon.ming.ai.rag.embedding import list_engines
        from src.com.damon.ming.log import pin

        engines = list_engines()
        if engines:
            pin("EmbeddingRegistry").info("[Registry] 可用 embedding 引擎: %s", engines)
        else:
            pin("EmbeddingRegistry").warning("[Registry] 未注册任何 embedding 引擎")
        self._items = EmbeddingConfigLoader().load_all()

    def get_huggingface(self) -> BaseEmbeddingService:
        if self._items is None:
            raise RuntimeError("RAG embedding尚未初始化")
        try:
            return self._items["huggingface"]
        except KeyError as exc:
            raise ValueError("缺少 RAG embedding配置: huggingface") from exc
