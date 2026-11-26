# app-server/src/com/damon/ming/ai/rag/embedding/embedding_gateway.py
"""按角色提供已配置的 embedding 服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.config import EmbeddingConfig
from src.com.damon.ming.ai.rag.embedding.params import EmbeddingRoleParams


class EmbeddingGateway:
    """统一 embedding 入口，后端由启动配置装配。"""

    def __init__(
        self,
        roles: dict[str, EmbeddingRoleParams],
    ) -> None:
        """按业务参数和网关参数装配各 embedding role。"""
        from src.com.damon.ming.ai.rag.embedding.vllm_embedding import VllmEmbedding

        self._models = {
            role: VllmEmbedding(params.embedding, params.gateway)
            for role, params in roles.items()
        }

    @classmethod
    def from_mapping(
        cls,
        raw: Any,
        *,
        model_root_dir: Path,
        base_url: str,
    ) -> EmbeddingGateway:
        """解析 RAG embedding 配置并装配各角色的服务。"""
        config = EmbeddingConfig.from_mapping(
            raw,
            base_url=base_url,
            cache_folder=str(model_root_dir / "embedding"),
        )
        return cls(config.roles)

    def get(self, role: str) -> BaseEmbeddingService:
        """获取角色对应的 embedding 服务。"""
        try:
            return self._models[role]
        except KeyError as exc:
            raise ValueError(f"未配置 embedding role: {role}") from exc

    def get_bge_m3(self) -> BaseEmbeddingService:
        return self.get("bge_m3")
