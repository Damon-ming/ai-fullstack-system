# app-server/src/com/damon/ming/ai/rag/embedding/vllm.py
"""通过 OpenAI 兼容接口调用 vLLM pooling embedding 服务。"""

from typing import Any

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.log import pin

logger = pin("VllmEmbedding")


class VllmEmbedding(BaseEmbeddingService):
    """将 embedding 请求转发到独立的 vLLM 服务。"""

    def __init__(self, params: EmbeddingParams):
        super().__init__(params)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("vLLM embedding 需要 openai Python SDK") from e

        self._base_url = params.extra["base_url"]
        self._api_key = params.extra["api_key"]
        self._timeout = params.extra["timeout"]
        self._max_input_tokens = params.extra["max_input_tokens"]
        self._dimension = params.extra.get("dimension")
        self._query_prefix = params.extra.get("query_prefix", "")
        self._passage_prefix = params.extra.get("passage_prefix", "")
        self._tokenizer = self._load_tokenizer(
            params.model_name,
            params.extra.get("cache_folder"),
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
        return self._max_input_tokens

    def get_tokenizer(self) -> Any:
        return self._tokenizer

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(self._query_prefix + text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        inputs = [self._passage_prefix + text for text in texts]
        try:
            response = self._client.embeddings.create(
                model=self.params.model_name,
                input=inputs,
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
            "query_prefix": self._query_prefix,
            "passage_prefix": self._passage_prefix,
        }

    def _embed_one(self, text: str) -> list[float]:
        try:
            response = self._client.embeddings.create(
                model=self.params.model_name,
                input=text,
                encoding_format="float",
            )
            return response.data[0].embedding
        except Exception as e:
            raise RuntimeError(f"vLLM embedding failed: {e}") from e
