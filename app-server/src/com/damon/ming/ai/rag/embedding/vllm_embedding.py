# app-server/src/com/damon/ming/ai/rag/embedding/vllm_embedding.py
"""通过 OpenAI 兼容接口调用 vLLM pooling embedding 服务。"""

from typing import Any

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.input_policy import EmbeddingInputPolicy
from src.com.damon.ming.ai.rag.embedding.params import (
    EmbeddingGatewayParams,
    EmbeddingParams,
)
from src.com.damon.ming.log import pin

logger = pin("VllmEmbedding")


class VllmEmbedding(BaseEmbeddingService):
    """将 embedding 请求转发到独立的 vLLM 服务。"""

    def __init__(
        self,
        params: EmbeddingParams,
        gateway_params: EmbeddingGatewayParams,
    ):
        if params.max_input_tokens is None:
            raise ValueError("vLLM embedding 必须配置 max_input_tokens")
        super().__init__(params)
        self._input_policy = EmbeddingInputPolicy(params)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("vLLM embedding 需要 openai Python SDK") from e

        self._base_url = gateway_params.base_url
        self._api_key = gateway_params.api_key
        self._timeout = gateway_params.timeout_seconds
        self._max_input_tokens = params.max_input_tokens
        self._dimension = params.dimension
        self._tokenizer = self._load_tokenizer(
            params.model_name,
            params.cache_folder,
        )
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=self._timeout,
        )
        logger.info(
            "[VllmEmbedding] 初始化成功 | model=%s | url=%s | max_input_tokens=%s",
            params.model_name,
            self._base_url,
            self._max_input_tokens,
        )

    @staticmethod
    def _load_tokenizer(model_name: str, cache_folder: str | None) -> Any:
        try:
            from transformers import AutoTokenizer
        except ImportError as e:
            raise ImportError("vLLM embedding 分块需要 transformers") from e

        return AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_folder or None,
            use_fast=True,
        )

    @property
    def max_input_tokens(self) -> int:
        return self._input_policy.available_document_tokens(
            self._max_input_tokens, self._tokenizer
        )

    def get_tokenizer(self) -> Any:
        return self._tokenizer

    def embed_query(self, text: str) -> list[float]:
        return self._input_policy.embed_query(text, self._embed_query)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._input_policy.embed_documents(texts, self._embed_documents_batch)

    def _embed_query(self, text: str) -> list[float]:
        try:
            response = self._client.embeddings.create(
                model=self.params.model_name,
                input=text,
                encoding_format="float",
            )
            return response.data[0].embedding
        except Exception as e:
            raise RuntimeError(f"vLLM embedding failed: {e}") from e

    def _embed_documents_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(
                model=self.params.model_name,
                input=texts,
                encoding_format="float",
            )
            return [
                item.embedding
                for item in sorted(response.data, key=lambda item: item.index)
            ]
        except Exception as e:
            raise RuntimeError(f"vLLM batch embedding failed: {e}") from e

    def get_model_info(self) -> dict:
        return {
            "provider": "vllm",
            "model": self.params.model_name,
            "base_url": self._base_url,
            "dimension": self._dimension,
            "max_input_tokens": self._max_input_tokens,
            "query_prefix": self.params.query_prefix,
            "passage_prefix": self.params.passage_prefix,
        }
