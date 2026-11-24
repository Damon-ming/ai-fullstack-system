# app-server/src/com/damon/ming/ai/rag/embedding/embedding_gateway.py
"""按角色提供已配置的 embedding 服务。"""

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.config.embedding_config_loader import (
    EmbeddingBusinessConfigLoader,
)


class EmbeddingGateway:
    """统一 embedding 入口，后端由启动配置装配。"""

    def __init__(self, roles: dict[str, dict]) -> None:
        """合并业务配置并按角色装配 embedding 引擎。"""
        from src.com.damon.ming.ai.rag.embedding.vllm_embedding import VllmEmbedding

        params = EmbeddingBusinessConfigLoader().load(roles)
        self._models = {role: VllmEmbedding(config) for role, config in params.items()}

    def get(self, role: str) -> BaseEmbeddingService:
        """获取角色对应的 embedding 服务。"""
        try:
            return self._models[role]
        except KeyError as exc:
            raise ValueError(f"未配置 embedding role: {role}") from exc

    def get_bge_m3(self) -> BaseEmbeddingService:
        return self.get("bge_m3")
