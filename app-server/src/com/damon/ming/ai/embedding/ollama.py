# app-server/src/com/damon/ming/ai/embedding/ollama.py

import hashlib
import threading
from collections import OrderedDict

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
      - embed_query 自动加 query_prefix，embed_documents 自动加 passage_prefix，
        与 BGE-M3 等模型的训练分布对齐，提升检索召回质量。
      - 前缀通过 YAML params.extra 配置，默认空字符串（不加），向后兼容。
      - 缓存 key 使用加前缀后的文本，避免裸文本命中错误缓存。
      - embed_query 自身不做 sleep 重试（避免阻塞线程池 worker），
        失败立即抛 RuntimeError，由上层调用方（DenseRetriever）做短退避重试。
      - 缓存使用 OrderedDict 实现 LRU 淘汰（上限通过 YAML cache_max 配置，默认 2000 条），
        防止长期运行后内存无界增长。
      - 缓存 key 使用 SHA-256（hexdigest 前 32 字符），避免 MD5 潜在碰撞风险。
    """

    def __init__(self, params: EmbeddingParams):
        super().__init__(params)
        try:
            import ollama
        except ImportError:
            raise ImportError("请安装 ollama: pip install ollama")

        self.client = ollama.Client(host=params.base_url, timeout=params.timeout)
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_lock = threading.Lock()
        # LRU 上限（YAML embedding-config.yaml params.cache_max 透传，默认 2000 条）
        self._cache_max = params.extra.get("cache_max", 2000)
        # BGE-M3 等模型要求的编码前缀（与训练分布对齐）
        self._query_prefix = params.extra.get("query_prefix", "")
        self._passage_prefix = params.extra.get("passage_prefix", "")

        # 验证模型是否可用
        try:
            self.client.embeddings(model=params.model_name, prompt="test")
            logger.info(
                "[OllamaEmbedding] 初始化成功 | model=%s | url=%s | "
                "query_prefix=%r | passage_prefix=%r",
                params.model_name,
                params.base_url,
                self._query_prefix,
                self._passage_prefix,
            )
        except Exception as e:
            logger.warning(
                "[OllamaEmbedding] 模型验证失败（可能未下载）| model=%s | error=%s",
                params.model_name,
                e,
            )

    def embed_query(self, text: str) -> list[float]:
        """单条 query 编码（自动加 query_prefix）。

        失败时立即抛 RuntimeError，由上层 DenseRetriever 做短退避重试，
        避免在 run_in_executor 的线程池 worker 内阻塞其他请求。
        """
        return self._embed_with_prefix(text, self._query_prefix)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文档编码（每条加 passage_prefix）。"""
        return [self._embed_with_prefix(text, self._passage_prefix) for text in texts]

    def get_model_info(self) -> dict:
        with self._cache_lock:
            cache_size = len(self._cache)
        return {
            "provider": "ollama",
            "model": self.params.model_name,
            "base_url": self.params.base_url,
            "dimension": None,
            "cache_size": cache_size,
            "cache_max": self._cache_max,
            "query_prefix": self._query_prefix,
            "passage_prefix": self._passage_prefix,
        }

    # ── 私有 ────────────────────────────────────────────────────────────

    def _embed_with_prefix(self, text: str, prefix: str) -> list[float]:
        """带前缀的编码（缓存 key 使用加前缀后的文本）。"""
        prefixed = prefix + text
        cache_key = hashlib.sha256(prefixed.encode("utf-8")).hexdigest()[:32]

        with self._cache_lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

        try:
            response = self.client.embeddings(
                model=self.params.model_name, prompt=prefixed
            )
            vector = response["embedding"]
            with self._cache_lock:
                self._cache[cache_key] = vector
                self._cache.move_to_end(cache_key)
                if len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)
            return vector
        except Exception as e:
            raise RuntimeError(f"Ollama embedding failed: {e}")
