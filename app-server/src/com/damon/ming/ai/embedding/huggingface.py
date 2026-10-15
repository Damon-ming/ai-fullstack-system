# app-server/src/com/damon/ming/ai/embedding/huggingface.py
from typing import List, Optional

from src.com.damon.ming.ai.embedding.BaseEmbeddingService import BaseEmbeddingService
from src.com.damon.ming.log import pin


class HuggingFaceEmbedding(BaseEmbeddingService):
    """
    HuggingFace 实现
    
    扩展方式：修改 model_name，支持所有 HF 模型
    """
    
    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cpu",
        normalize_embeddings: bool = True,
        cache_folder: Optional[str] = None
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("请安装 sentence-transformers: pip install sentence-transformers")
        
        self.logger = pin("HuggingFaceEmbedding")
        self.model_name = model_name
        self.device = device
        self.normalize_embeddings = normalize_embeddings
        
        # 加载模型（首次会下载）
        self.model = SentenceTransformer(
            model_name,
            device=device,
            cache_folder=cache_folder
        )
        
        self.logger.info(f"[HuggingFaceEmbedding] 初始化成功 | model={model_name} | device={device}")
    
    def embed_query(self, text: str) -> List[float]:
        try:
            embedding = self.model.encode(
                text,
                normalize_embeddings=self.normalize_embeddings
            )
            return embedding.tolist()
        except Exception as e:
            raise RuntimeError(f"HuggingFace embedding failed: {e}")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量向量化（性能优势）"""
        try:
            embeddings = self.model.encode(
                texts,
                normalize_embeddings=self.normalize_embeddings,
                show_progress_bar=False
            )
            return embeddings.tolist()
        except Exception as e:
            raise RuntimeError(f"HuggingFace batch embedding failed: {e}")
    
    def get_model_info(self) -> dict:
        return {
            "provider": "huggingface",
            "model": self.model_name,
            "device": self.device,
            "dimension": self.model.get_sentence_embedding_dimension(),
            "normalize": self.normalize_embeddings
        }
