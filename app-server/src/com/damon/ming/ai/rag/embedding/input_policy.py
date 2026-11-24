# app-server/src/com/damon/ming/ai/rag/embedding/input_policy.py
"""Embedding 角色的可选文本规则，不依赖具体推理后端。"""

from collections.abc import Callable
from typing import Any

from src.com.damon.ming.ai.rag.embedding.model_config import EmbeddingParams


class EmbeddingInputPolicy:
    """为一个已配置模型应用前缀、分批和输入窗口预留。"""

    def __init__(self, params: EmbeddingParams) -> None:
        if type(params.batch_size) is not int or params.batch_size < 1:
            raise ValueError("embedding batch_size 必须是正整数")
        if not isinstance(params.query_prefix, str) or not isinstance(
            params.passage_prefix, str
        ):
            raise TypeError("embedding 文本前缀必须是字符串")
        self._query_prefix = params.query_prefix
        self._passage_prefix = params.passage_prefix
        self._batch_size = params.batch_size

    def embed_query(
        self, text: str, encode: Callable[[str], list[float]]
    ) -> list[float]:
        return encode(self._query_prefix + text)

    def embed_documents(
        self,
        texts: list[str],
        encode_batch: Callable[[list[str]], list[list[float]]],
    ) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            result = encode_batch([self._passage_prefix + text for text in batch])
            if len(result) != len(batch):
                raise ValueError("embedding 服务返回的向量数量与请求不一致")
            embeddings.extend(result)
        return embeddings

    def available_document_tokens(self, limit: int, tokenizer: Any | None) -> int:
        """估算扣除文档前缀后的正文上限。"""
        if not self._passage_prefix:
            return limit
        if tokenizer is None:
            raise ValueError("配置文档前缀时需要 tokenizer 计算输入上限")
        # 拼接可能改变分词边界；8 token 是经验余量，不是精确校验。
        available = (
            limit
            - len(tokenizer.encode(self._passage_prefix, add_special_tokens=False))
            - 8
        )
        if available <= 0:
            raise ValueError("Embedding 模型输入上限不足以容纳文档前缀")
        return available
