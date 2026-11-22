"""RAG embedding 模型的初始化和访问入口。"""

from pathlib import Path

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.config.embedding_config_loader import (
    EmbeddingConfigLoader,
)
from src.com.damon.ming.ai.rag.embedding.embedding_engine import EmbeddingEngine


class RagEmbedders:
    def __init__(self) -> None:
        self._embedder: BaseEmbeddingService | None = None

    def initialize(self, engine: EmbeddingEngine, model_root_dir: Path) -> None:
        if self._embedder is not None:
            raise RuntimeError("RAG embedding已经初始化")
        from src.com.damon.ming.ai.rag.embedding import list_engines
        from src.com.damon.ming.log import pin

        engines = list_engines()
        if engines:
            pin("EmbeddingRegistry").info("[Registry] 可用 embedding 引擎: %s", engines)
        else:
            pin("EmbeddingRegistry").warning("[Registry] 未注册任何 embedding 引擎")
        self._embedder = EmbeddingConfigLoader().load(engine, model_root_dir)

    def get_embedding(self) -> BaseEmbeddingService:
        if self._embedder is None:
            raise RuntimeError("RAG embedding尚未初始化")
        return self._embedder
