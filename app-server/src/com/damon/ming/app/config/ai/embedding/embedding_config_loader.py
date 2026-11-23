"""按 Gateway 角色配置和 RAG 业务配置装配 embedding 模型。"""

from pathlib import Path

from src.com.damon.ming.ai.rag.embedding import VllmEmbedding
from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.ai.rag.embedding.config.embedding_config_loader import (
    EmbeddingBusinessConfigLoader,
)
from src.com.damon.ming.app.config.env import get_inference_gateway_url
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class EmbeddingConfigLoader:
    """按角色装配模型；Gateway 连接和 RAG 文本参数分别读取。"""

    def __init__(self, config_path: str | None = None) -> None:
        directory = config_path or str(Path(__file__).resolve().parent)
        self._config_path = resolve_yaml_path(directory)

    def load(self, model_root_dir: Path) -> dict[str, BaseEmbeddingService]:
        """装配配置中的角色，按角色名返回后端实例。"""
        raw = load_yaml(self._config_path)
        if not isinstance(raw, dict):
            raise TypeError("Embedding Gateway 配置必须是 YAML 对象")
        transport = raw.get("transport")
        roles = raw.get("roles")
        if not isinstance(transport, dict):
            raise TypeError("Embedding Gateway 配置缺少 transport")
        if not isinstance(roles, dict) or not roles:
            raise ValueError("Embedding Gateway 配置缺少 roles")

        common = EmbeddingBusinessConfigLoader().load()
        base_url = get_inference_gateway_url()
        loaded: dict[str, BaseEmbeddingService] = {}
        for role, entry in roles.items():
            if not isinstance(entry, dict):
                raise TypeError(f"Embedding role '{role}' 配置必须是 YAML 对象")
            model_name = entry.get("model_name")
            if not isinstance(model_name, str) or not model_name.strip():
                raise ValueError(f"Embedding role '{role}' 缺少有效的 model_name")

            extra = dict(common)
            extra.update(
                base_url=base_url,
                timeout=transport["timeout_seconds"],
                api_key=entry["api_key"],
                max_input_tokens=entry["max_input_tokens"],
                dimension=entry["dimension"],
            )
            extra["cache_folder"] = str(model_root_dir / "embedding")
            params = EmbeddingParams(model_name=model_name, extra=extra)
            loaded[role] = VllmEmbedding(params)
        return loaded
