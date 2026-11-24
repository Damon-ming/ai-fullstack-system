"""合并并校验 embedding 模型参数与业务配置。"""

from pathlib import Path

from src.com.damon.ming.ai.rag.embedding.model_config import VLLMEmbeddingParams
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class EmbeddingBusinessConfigLoader:
    def __init__(self, config_path: str | None = None) -> None:
        directory = config_path or str(Path(__file__).resolve().parent)
        self._config_path = resolve_yaml_path(directory)

    def load(self, roles: dict[str, dict]) -> dict[str, VLLMEmbeddingParams]:
        """按同名 role 合并应用层参数与模型各自的文本规则。"""
        if not roles:
            raise ValueError("Embedding Gateway 配置缺少 roles")
        raw = load_yaml(self._config_path)
        if not isinstance(raw, dict):
            raise TypeError("RAG embedding 配置必须是 YAML 对象")
        business_roles = raw.get("roles")
        if not isinstance(business_roles, dict) or not business_roles:
            raise ValueError("RAG embedding 配置缺少 roles")
        missing = roles.keys() - business_roles.keys()
        extra = business_roles.keys() - roles.keys()
        if missing or extra:
            raise ValueError(
                "Embedding 角色配置不一致 | "
                f"缺少业务配置: {sorted(missing)} | 未装配的业务配置: {sorted(extra)}"
            )

        loaded: dict[str, VLLMEmbeddingParams] = {}
        for role, values in roles.items():
            business = business_roles[role]
            if not isinstance(business, dict):
                raise TypeError(f"Embedding role '{role}' 的业务配置必须是 YAML 对象")
            batch_size = business.get("batch_size")
            query_prefix = business.get("query_prefix", "")
            passage_prefix = business.get("passage_prefix", "")
            if type(batch_size) is not int or batch_size < 1:
                raise ValueError(f"Embedding role '{role}' 的 batch_size 必须是正整数")
            if not isinstance(query_prefix, str) or not isinstance(passage_prefix, str):
                raise TypeError(f"Embedding role '{role}' 的文本前缀必须是字符串")
            loaded[role] = VLLMEmbeddingParams(
                **values,
                batch_size=batch_size,
                query_prefix=query_prefix,
                passage_prefix=passage_prefix,
            )
        return loaded
