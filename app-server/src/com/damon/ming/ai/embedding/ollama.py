# app-server/src/com/damon/ming/ai/embedding/ollama.py

import hashlib
import time

from src.com.damon.ming.ai.embedding import register_engine
from src.com.damon.ming.ai.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.log import pin

logger = pin("OllamaEmbedding")


@register_engine("ollama")
class OllamaEmbedding(BaseEmbeddingService):
    """Ollama embedding — 适用于 Ollama 服务托管的 embedding 模型"""

    def __init__(self, params: EmbeddingParams):
        super().__init__(params)
        try:
            import ollama
        except ImportError:
            raise ImportError("请安装 ollama: pip install ollama")

        self.client = ollama.Client(host=params.base_url, timeout=params.timeout)
        self._cache: dict[str, list[float]] = {}

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
        cache_key = hashlib.md5(text.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        for attempt in range(self.params.max_retries):
            try:
                response = self.client.embeddings(
                    model=self.params.model_name, prompt=text
                )
                vector = response["embedding"]
                self._cache[cache_key] = vector
                return vector
            except Exception as e:
                if attempt == self.params.max_retries - 1:
                    raise RuntimeError(
                        f"Ollama embedding failed after {self.params.max_retries} attempts: {e}"
                    )
                wait_time = 2**attempt
                logger.warning(
                    f"重试 {attempt + 1}/{self.params.max_retries}，等待 {wait_time}s"
                )
                time.sleep(wait_time)

        raise RuntimeError("Unexpected error in embed_query")

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
