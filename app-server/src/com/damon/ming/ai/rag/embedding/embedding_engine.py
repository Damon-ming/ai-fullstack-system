"""可选的 RAG embedding 引擎。"""

from enum import Enum


class EmbeddingEngine(str, Enum):
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
