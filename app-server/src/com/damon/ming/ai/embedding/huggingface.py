# app-server/src/com/damon/ming/ai/embedding/huggingface.py

import threading

from src.com.damon.ming.ai.embedding import register_engine
from src.com.damon.ming.ai.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.log import pin

logger = pin("HuggingFaceEmbedding")


@register_engine("huggingface")
class HuggingFaceEmbedding(BaseEmbeddingService):
    """HuggingFace embedding — 适用于本地 GPU/CPU 推理的 SentenceTransformer 模型。

    并发控制：
      - embed_query（单条）无锁：PyTorch no_grad 推理在单条场景下线程安全，
        锁会串行化 retrieval 池的全部并发能力。
      - embed_documents（批量）用 threading.Semaphore(params.concurrency) 限流：
        多个 batch 同时 GPU 推理会争抢 CUDA context，并发上限由 YAML 配置透传。
    """

    def __init__(self, params: EmbeddingParams):
        super().__init__(params)
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "请安装 sentence-transformers: pip install sentence-transformers"
            )

        self.model = SentenceTransformer(
            params.model_name,
            device=params.device,
            cache_folder=params.cache_folder or None,
        )
        # BGE-M3 等模型要求的编码前缀（与训练分布对齐）
        self._query_prefix = params.extra.get("query_prefix", "")
        self._passage_prefix = params.extra.get("passage_prefix", "")
        # 批量推理并发控制（仅 batch 模式使用，单条 embed_query 无锁）
        self._batch_sem = threading.Semaphore(params.concurrency)
        logger.info(
            f"[HuggingFaceEmbedding] 初始化成功 | model={params.model_name} | "
            f"device={params.device} | concurrency={params.concurrency} | "
            f"query_prefix={self._query_prefix!r} | passage_prefix={self._passage_prefix!r}"
        )

    def embed_query(self, text: str) -> list[float]:
        """单条推理无锁，自动加 query_prefix。"""
        try:
            text = self._query_prefix + text
            embedding = self.model.encode(
                text, normalize_embeddings=self.params.normalize_embeddings
            )
            return embedding.tolist()
        except Exception as e:
            raise RuntimeError(f"HuggingFace embedding failed: {e}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量推理受 concurrency 信号量限流，每条自动加 passage_prefix。"""
        try:
            texts = [self._passage_prefix + t for t in texts]
            with self._batch_sem:
                embeddings = self.model.encode(
                    texts,
                    normalize_embeddings=self.params.normalize_embeddings,
                    show_progress_bar=False,
                )
            return embeddings.tolist()
        except Exception as e:
            raise RuntimeError(f"HuggingFace batch embedding failed: {e}")

    def get_model_info(self) -> dict:
        return {
            "provider": "huggingface",
            "model": self.params.model_name,
            "device": self.params.device,
            "dimension": self.model.get_sentence_embedding_dimension(),
            "normalize": self.params.normalize_embeddings,
            "query_prefix": self._query_prefix,
            "passage_prefix": self._passage_prefix,
        }
