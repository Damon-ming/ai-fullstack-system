"""解析 embedding YAML，组合各角色的业务参数与网关参数。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.ai.rag.embedding.params import (
    EmbeddingGatewayParams,
    EmbeddingParams,
    EmbeddingRoleParams,
)


@dataclass(frozen=True, kw_only=True)
class EmbeddingConfig:
    roles: dict[str, EmbeddingRoleParams]

    def __post_init__(self) -> None:
        if not isinstance(self.roles, dict) or not self.roles:
            raise ValueError("RAG embedding 配置缺少 roles")
        if not all(
            isinstance(params, EmbeddingRoleParams) for params in self.roles.values()
        ):
            raise TypeError("RAG embedding roles 必须使用 EmbeddingRoleParams")

    @classmethod
    def from_mapping(
        cls,
        raw: Any,
        *,
        base_url: str,
    ) -> EmbeddingConfig:
        """解析 YAML 的缓存目录和角色配置，注入应用提供的网关地址。"""
        if not isinstance(raw, dict):
            raise TypeError("RAG embedding 配置必须是 YAML 对象")
        cache_folder = raw.get("cache_folder")
        if not isinstance(cache_folder, str) or not cache_folder.strip():
            raise ValueError("RAG embedding.cache_folder 必须是非空字符串")
        transport = raw.get("transport")
        if not isinstance(transport, dict):
            raise TypeError("Embedding 配置缺少 transport")
        roles_raw = raw.get("roles")
        if not isinstance(roles_raw, dict) or not roles_raw:
            raise ValueError("RAG embedding 配置缺少 roles")

        roles: dict[str, EmbeddingRoleParams] = {}
        for role, entry in roles_raw.items():
            if not isinstance(entry, dict):
                raise TypeError(f"Embedding role '{role}' 配置必须是 YAML 对象")
            try:
                max_model_len = entry.get("max_model_len")
                if type(max_model_len) is not int or max_model_len <= 0:
                    raise ValueError("max_model_len 必须是正整数")
                max_input_tokens = entry.get("max_input_tokens")
                if type(max_input_tokens) is not int or max_input_tokens <= 0:
                    raise ValueError("max_input_tokens 必须是正整数")
                if max_input_tokens > max_model_len:
                    raise ValueError("max_input_tokens 不能大于 max_model_len")
                roles[role] = EmbeddingRoleParams(
                    embedding=EmbeddingParams(
                        model_name=entry.get("model_name"),
                        dimension=entry.get("dimension"),
                        batch_size=entry.get("batch_size"),
                        query_prefix=entry.get("query_prefix", ""),
                        passage_prefix=entry.get("passage_prefix", ""),
                        max_input_tokens=max_input_tokens,
                        cache_folder=cache_folder,
                    ),
                    gateway=EmbeddingGatewayParams(
                        base_url=base_url,
                        api_key=entry.get("api_key"),
                        timeout_seconds=transport.get("timeout_seconds"),
                    ),
                )
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"Embedding role '{role}' 配置无效: {exc}") from exc
        return cls(roles=roles)
