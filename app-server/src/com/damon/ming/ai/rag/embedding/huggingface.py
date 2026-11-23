# app-server/src/com/damon/ming/ai/rag/embedding/huggingface.py

import threading

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.model_config import HuggingFaceEmbeddingParams
from src.com.damon.ming.log import pin

logger = pin("HuggingFaceEmbedding")


class HuggingFaceEmbedding(BaseEmbeddingService):
    """HuggingFace embedding — 适用于本地 GPU/CPU 推理的 SentenceTransformer 模型。

    并发控制：
      - embed_query（单条）无锁：PyTorch no_grad 推理在单条场景下线程安全，
        锁会串行化 retrieval 池的全部并发能力。
      - embed_documents（批量）用 threading.Semaphore(concurrency) 限流：
        多个 batch 同时 GPU 推理会争抢 CUDA context，并发上限由 YAML 配置透传。
    """

    def __init__(self, params: HuggingFaceEmbeddingParams):
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
        self._normalize_embeddings = params.normalize_embeddings
        concurrency = params.concurrency
        # 批量推理并发控制（仅 batch 模式使用，单条 embed_query 无锁）
        self._batch_sem = threading.Semaphore(concurrency)
        logger.info(
            f"[HuggingFaceEmbedding] 初始化成功 | model={params.model_name} | "
            f"device={params.device} | concurrency={concurrency}"
        )

    def embed_query(self, text: str) -> list[float]:
        """单条推理无锁。"""
        try:
            embedding = self.model.encode(
                text, normalize_embeddings=self._normalize_embeddings
            )
            return embedding.tolist()
        except Exception as e:
            raise RuntimeError(f"HuggingFace embedding failed: {e}")

    @property
    def max_input_tokens(self) -> int | None:
        """返回扣除特殊 token 和边界余量后的输入 token 上限。"""
        model_limit = getattr(self.model, "max_seq_length", None)
        if not isinstance(model_limit, int) or model_limit <= 0:
            return None
        special_tokens = self.model.tokenizer.num_special_tokens_to_add(pair=False)
        # 文本前缀与正文拼接处可能改变少量子词边界，预留 8 token 防止模型静默截断。
        boundary_margin = 8
        available_tokens = model_limit - special_tokens - boundary_margin
        if available_tokens <= 0:
            raise ValueError("Embedding 模型窗口不足以容纳前缀、特殊 token 和安全余量")
        return available_tokens

    def get_tokenizer(self):
        """返回 SentenceTransformer 实际用于编码的 tokenizer。"""
        return self.model.tokenizer

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量推理受 concurrency 信号量限流。"""
        try:
            with self._batch_sem:
                embeddings = self.model.encode(
                    texts,
                    normalize_embeddings=self._normalize_embeddings,
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
            "normalize": self._normalize_embeddings,
        }
