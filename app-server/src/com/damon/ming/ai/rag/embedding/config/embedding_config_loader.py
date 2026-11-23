"""合并并校验 embedding 模型参数与业务配置。"""

from pathlib import Path

from src.com.damon.ming.ai.rag.embedding.model_config import VLLMEmbeddingParams
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class EmbeddingBusinessConfigLoader:
    def __init__(self, config_path: str | None = None) -> None:
        directory = config_path or str(Path(__file__).resolve().parent)
        self._config_path = resolve_yaml_path(directory)

    def load(self, roles: dict[str, dict]) -> dict[str, VLLMEmbeddingParams]:
        """为每个角色合并应用层参数及共用的业务配置。"""
        if not roles:
            raise ValueError("Embedding Gateway 配置缺少 roles")
        raw = load_yaml(self._config_path)
        if not isinstance(raw, dict):
            raise TypeError("RAG embedding 配置必须是 YAML 对象")
        if "batch_size" not in raw:
            raise ValueError("RAG embedding 配置缺少 batch_size")
        batch_size = raw["batch_size"]
        query_prefix = raw.get("query_prefix", "")
        passage_prefix = raw.get("passage_prefix", "")
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("embedding batch_size 必须是正整数")
        if not isinstance(query_prefix, str) or not isinstance(passage_prefix, str):
            raise TypeError("embedding 文本前缀必须是字符串")
        return {
            role: VLLMEmbeddingParams(
                **values,
                batch_size=batch_size,
                query_prefix=query_prefix,
                passage_prefix=passage_prefix,
            )
            for role, values in roles.items()
        }
