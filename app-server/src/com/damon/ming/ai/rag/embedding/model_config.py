"""Embedding 各推理引擎的参数。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmbeddingParams:
    """各 embedding 引擎共享的模型参数。"""

    model_name: str
    batch_size: int = field(kw_only=True)
    query_prefix: str = field(kw_only=True)
    passage_prefix: str = field(kw_only=True)
    cache_folder: str | None = field(default=None, kw_only=True)


@dataclass(frozen=True)
class VLLMEmbeddingParams(EmbeddingParams):
    base_url: str
    api_key: str
    timeout: float
    max_input_tokens: int
    dimension: int


@dataclass(frozen=True)
class HuggingFaceEmbeddingParams(EmbeddingParams):
    device: str
    concurrency: int
    normalize_embeddings: bool
