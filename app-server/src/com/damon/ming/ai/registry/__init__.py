# app-server/src/com/damon/ming/ai/registry/__init__.py
from src.com.damon.ming.ai.registry.db_registry import register_all_vector_dbs
from src.com.damon.ming.ai.registry.embedding_registry import register_all_embeddings
from src.com.damon.ming.ai.registry.inference_registry import register_all_inferences
from src.com.damon.ming.ai.registry.rerank_registry import register_all_rerankers
from src.com.damon.ming.ai.registry.summary_registry import register_all_summarizers
from src.com.damon.ming.ai.registry.tokenizer_registry import register_all_tokenizers

__all__ = [
    "register_all_embeddings",
    "register_all_inferences",
    "register_all_rerankers",
    "register_all_summarizers",
    "register_all_tokenizers",
    "register_all_vector_dbs",
]
