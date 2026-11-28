"""Runtime parameters for embedding behavior and gateway access."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class EmbeddingParams:
    """Business and model parameters shared by embedding implementations."""

    model_name: str
    dimension: int
    max_model_len: int
    batch_size: int
    query_prefix: str
    passage_prefix: str
    cache_folder: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name 必须是非空字符串")
        for name, value in (
            ("dimension", self.dimension),
            ("max_model_len", self.max_model_len),
            ("batch_size", self.batch_size),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} 必须是正整数")
        if not isinstance(self.query_prefix, str) or not isinstance(
            self.passage_prefix, str
        ):
            raise TypeError("文本前缀必须是字符串")


@dataclass(frozen=True, kw_only=True)
class EmbeddingGatewayParams:
    """Connection and authentication parameters for the embedding API."""

    base_url: str
    api_key: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ValueError("base_url 必须是非空字符串")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key 必须是非空字符串")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds 必须是有限正数")


@dataclass(frozen=True, kw_only=True)
class EmbeddingRoleParams:
    """同一角色的 embedding 业务参数和网关连接参数。"""

    embedding: EmbeddingParams
    gateway: EmbeddingGatewayParams

    def __post_init__(self) -> None:
        if not isinstance(self.embedding, EmbeddingParams):
            raise TypeError("embedding 必须使用 EmbeddingParams")
        if not isinstance(self.gateway, EmbeddingGatewayParams):
            raise TypeError("gateway 必须使用 EmbeddingGatewayParams")


@dataclass(frozen=True, kw_only=True)
class HuggingFaceEmbeddingParams(EmbeddingParams):
    device: str
    concurrency: int
    normalize_embeddings: bool

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.device, str) or not self.device.strip():
            raise ValueError("device 必须是非空字符串")
        if type(self.concurrency) is not int or self.concurrency <= 0:
            raise ValueError("concurrency 必须是正整数")
        if not isinstance(self.normalize_embeddings, bool):
            raise TypeError("normalize_embeddings 必须是布尔值")
