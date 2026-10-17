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
    """HuggingFace embedding — 适用于本地 GPU/CPU 推理的 SentenceTransformer 模型"""

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
        # SentenceTransformer.encode 底层为 PyTorch forward，非线程安全
        self._infer_lock = threading.Lock()
        logger.info(
            f"[HuggingFaceEmbedding] 初始化成功 | model={params.model_name} | device={params.device}"
        )

    def embed_query(self, text: str) -> list[float]:
        try:
            with self._infer_lock:
                embedding = self.model.encode(
                    text, normalize_embeddings=self.params.normalize_embeddings
                )
            return embedding.tolist()
        except Exception as e:
            raise RuntimeError(f"HuggingFace embedding failed: {e}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            with self._infer_lock:
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
        }
