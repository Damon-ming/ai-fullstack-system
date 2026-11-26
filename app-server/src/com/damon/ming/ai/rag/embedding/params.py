"""Immutable initialization parameters shared by embedding engines."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmbeddingParams:
    """各 embedding 引擎共享的完整初始化参数。"""

    model_name: str
    dimension: int = field(kw_only=True)
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


@dataclass(frozen=True)
class HuggingFaceEmbeddingParams(EmbeddingParams):
    device: str
    concurrency: int
    normalize_embeddings: bool
