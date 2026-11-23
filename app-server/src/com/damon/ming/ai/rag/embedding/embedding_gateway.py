# app-server/src/com/damon/ming/ai/rag/embedding/embedding_gateway.py
"""RAG embedding 统一调用入口。"""

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)


class EmbeddingGateway:
    """按角色提供 embedding 后端，与推理 Gateway 的 role 映射对应。"""

    def __init__(self, models: dict[str, BaseEmbeddingService]) -> None:
        if not models:
            raise ValueError("EmbeddingGateway 至少需要一个已装配模型")
        self._models = dict(models)

    def get(self, role: str) -> BaseEmbeddingService:
        """按配置中的角色名取得 embedding 模型。"""
        try:
            return self._models[role]
        except KeyError as exc:
            raise ValueError(f"未配置 embedding role: {role}") from exc

    def get_bge_m3(self) -> BaseEmbeddingService:
        """获取 RAG 当前使用的 BGE-M3 embedding 模型。"""
        return self.get("bge_m3")
