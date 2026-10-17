# app-server/src/com/damon/ming/ai/embedding/ollama.py

import hashlib
import threading

from src.com.damon.ming.ai.embedding import register_engine
from src.com.damon.ming.ai.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.log import pin

logger = pin("OllamaEmbedding")


@register_engine("ollama")
class OllamaEmbedding(BaseEmbeddingService):
    """Ollama embedding — 适用于 Ollama 服务托管的 embedding 模型

    设计说明：
      - embed_query 自身不做 sleep 重试（避免阻塞线程池 worker），
        失败立即抛 RuntimeError，由上层调用方（DenseRetriever）做短退避重试。
      - 缓存只增不减，注意内存上限（当前场景 query 多样性可控）。
    """

    def __init__(self, params: EmbeddingParams):
        super().__init__(params)
        try:
            import ollama
        except ImportError:
            raise ImportError("请安装 ollama: pip install ollama")

        self.client = ollama.Client(host=params.base_url, timeout=params.timeout)
        self._cache: dict[str, list[float]] = {}
        self._cache_lock = threading.Lock()

        # 验证模型是否可用
        try:
            self.client.embeddings(model=params.model_name, prompt="test")
            logger.info(
                f"[OllamaEmbedding] 初始化成功 | model={params.model_name} | url={params.base_url}"
            )
        except Exception as e:
            logger.warning(
                f"[OllamaEmbedding] 模型验证失败（可能未下载）| model={params.model_name} | error={e}"
            )

    def embed_query(self, text: str) -> list[float]:
        """单条文本向量化（快速失败，不做 sleep 重试）。

        失败时立即抛 RuntimeError，由上层 DenseRetriever 做短退避重试，
        避免在 run_in_executor 的线程池 worker 内阻塞其他请求。
        """
        cache_key = hashlib.md5(text.encode("utf-8")).hexdigest()
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            response = self.client.embeddings(
                model=self.params.model_name, prompt=text
            )
            vector = response["embedding"]
            with self._cache_lock:
                self._cache[cache_key] = vector
            return vector
        except Exception as e:
            raise RuntimeError(f"Ollama embedding failed: {e}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def get_model_info(self) -> dict:
        return {
            "provider": "ollama",
            "model": self.params.model_name,
            "base_url": self.params.base_url,
            "dimension": None,
            "cache_size": len(self._cache),
        }
