# app-server/src/com/damon/ming/ai/embedding/ollama.py
import hashlib
import time
from typing import List

from src.com.damon.ming.ai.embedding.BaseEmbeddingService import BaseEmbeddingService
from src.com.damon.ming.log import pin


class OllamaEmbedding(BaseEmbeddingService):
    """
    Ollama 统一实现（支持 nomic-embed-text, bge-m3 等所有 Ollama 模型）
    
    扩展方式：只需修改 model_name 参数
    """
    
    def __init__(
        self, 
        model_name: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3
    ):
        try:
            import ollama
        except ImportError:
            raise ImportError("请安装 ollama: pip install ollama")
        
        self.logger = pin("OllamaEmbedding")
        self.model_name = model_name
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = ollama.Client(host=base_url, timeout=timeout)
        self._cache = {}
        
        # 验证模型是否存在
        try:
            self.client.embeddings(model=model_name, prompt="test")
            self.logger.info(f"[OllamaEmbedding] 初始化成功 | model={model_name} | url={base_url}")
        except Exception as e:
            self.logger.warning(f"[OllamaEmbedding] 模型验证失败（可能未下载）| model={model_name} | error={e}")
    
    def embed_query(self, text: str) -> List[float]:
        # 简单缓存
        cache_key = hashlib.md5(text.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 重试机制
        for attempt in range(self.max_retries):
            try:
                response = self.client.embeddings(
                    model=self.model_name, 
                    prompt=text
                )
                vector = response['embedding']
                self._cache[cache_key] = vector
                return vector
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"Ollama embedding failed after {self.max_retries} attempts: {e}"
                    )
                wait_time = 2 ** attempt
                self.logger.warning(f"重试 {attempt+1}/{self.max_retries}，等待 {wait_time}s")
                time.sleep(wait_time)
        
        # 理论上不会执行到这里
        raise RuntimeError("Unexpected error in embed_query")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量向量化（串行调用）"""
        return [self.embed_query(text) for text in texts]
    
    def get_model_info(self) -> dict:
        return {
            "provider": "ollama",
            "model": self.model_name,
            "base_url": self.base_url,
            "dimension": None,
            "cache_size": len(self._cache)
        }
