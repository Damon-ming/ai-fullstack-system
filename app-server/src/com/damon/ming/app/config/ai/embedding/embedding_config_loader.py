# app-server/src/com/damon/ming/app/config/ai/embedding/embedding_config_loader.py
"""加载并校验 embedding 模型配置。"""

from pathlib import Path

from src.com.damon.ming.app.config.ai_runtime_config import (
    get_model_dimension,
    get_model_max_input_tokens,
    get_model_max_len,
)
from src.com.damon.ming.app.config.env import (
    get_inference_gateway_url,
)
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class EmbeddingConfigLoader:
    """读取各角色的模型配置。"""

    def __init__(self, config_path: str | None = None) -> None:
        directory = config_path or str(Path(__file__).resolve().parent)
        self._config_path = resolve_yaml_path(directory)

    def load(self, model_root_dir: Path) -> dict[str, dict]:
        """按角色名返回经过校验的模型配置。"""
        raw = load_yaml(self._config_path)
        if not isinstance(raw, dict):
            raise TypeError("Embedding Gateway 配置必须是 YAML 对象")
        transport = raw.get("transport")
        roles = raw.get("roles")
        if not isinstance(transport, dict):
            raise TypeError("Embedding Gateway 配置缺少 transport")
        if not isinstance(roles, dict) or not roles:
            raise ValueError("Embedding Gateway 配置缺少 roles")

        base_url = get_inference_gateway_url()
        cache_folder = str(model_root_dir / "embedding")
        loaded: dict[str, dict] = {}
        for role, entry in roles.items():
            if not isinstance(entry, dict):
                raise TypeError(f"Embedding role '{role}' 配置必须是 YAML 对象")
            model_name = entry.get("model_name")
            if not isinstance(model_name, str) or not model_name.strip():
                raise ValueError(f"Embedding role '{role}' 缺少有效的 model_name")

            api_key = entry.get("api_key")
            max_tokens = get_model_max_input_tokens(model_name)
            dimension = get_model_dimension(model_name)
            max_model_len = get_model_max_len(model_name)
            timeout = transport.get("timeout_seconds")
            if not isinstance(api_key, str) or not api_key.strip():
                raise ValueError(f"Embedding role '{role}' 的 api_key 必须是非空字符串")
            if type(max_tokens) is not int or max_tokens <= 0:
                raise ValueError(
                    f"Embedding role '{role}' 的 max_input_tokens 必须是正整数"
                )
            if type(dimension) is not int or dimension <= 0:
                raise ValueError(f"Embedding role '{role}' 的 dimension 必须是正整数")
            if max_tokens > max_model_len:
                raise ValueError(
                    f"Embedding role '{role}' 的 max_input_tokens 不能大于模型 max-model-len"
                )
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not 0 < timeout < float("inf")
            ):
                raise ValueError("Embedding transport.timeout_seconds 必须是有限正数")
            params = {
                "model_name": model_name,
                "base_url": base_url,
                "api_key": api_key,
                "timeout": timeout,
                "max_input_tokens": max_tokens,
                "dimension": dimension,
                "cache_folder": cache_folder,
            }
            loaded[role] = params
        return loaded
