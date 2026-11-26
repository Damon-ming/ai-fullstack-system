# app-server/src/com/damon/ming/ai/rag/embedding/embedding_gateway.py
"""按角色提供已配置的 embedding 服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.config import (
    EmbeddingConfig,
)
from src.com.damon.ming.ai.rag.embedding.params import (
    EmbeddingGatewayParams,
    EmbeddingParams,
)


class EmbeddingGateway:
    """统一 embedding 入口，后端由启动配置装配。"""

    def __init__(
        self,
        embedding_params: dict[str, EmbeddingParams],
        gateway_params: dict[str, EmbeddingGatewayParams],
    ) -> None:
        """按业务参数和网关参数装配各 embedding role。"""
        from src.com.damon.ming.ai.rag.embedding.vllm_embedding import VllmEmbedding

        if embedding_params.keys() != gateway_params.keys():
            raise ValueError("embedding 业务参数和网关参数的 roles 必须一致")
        self._models = {
            role: VllmEmbedding(embedding_config, gateway_params[role])
            for role, embedding_config in embedding_params.items()
        }

    # todo :看下怎么处理这个问题
    @classmethod
    def from_mapping(
        cls,
        raw: Any,
        *,
        model_root_dir: Path,
        base_url: str,
    ) -> EmbeddingGateway:
        """解析 RAG embedding 配置并装配各角色的服务。"""
        config = EmbeddingConfig.from_mapping(raw)
        cache_folder = str(model_root_dir / "embedding")
        embedding_params = {
            role: EmbeddingParams(
                model_name=role_config.model_name,
                dimension=role_config.dimension,
                max_input_tokens=role_config.max_input_tokens,
                batch_size=role_config.batch_size,
                query_prefix=role_config.query_prefix,
                passage_prefix=role_config.passage_prefix,
                cache_folder=cache_folder,
            )
            for role, role_config in config.roles.items()
        }
        gateway_params = {
            role: EmbeddingGatewayParams(
                base_url=base_url,
                api_key=role_config.api_key,
                timeout_seconds=config.transport.timeout_seconds,
            )
            for role, role_config in config.roles.items()
        }
        return cls(embedding_params, gateway_params)

    def get(self, role: str) -> BaseEmbeddingService:
        """获取角色对应的 embedding 服务。"""
        try:
            return self._models[role]
        except KeyError as exc:
            raise ValueError(f"未配置 embedding role: {role}") from exc

    def get_bge_m3(self) -> BaseEmbeddingService:
        return self.get("bge_m3")
