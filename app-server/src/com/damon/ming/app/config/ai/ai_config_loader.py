"""对外统一加载 app-server 所需的 AI 配置。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.app.config.ai.inference.inference_config_loader import (
    InferenceConfigLoader,
)
from src.com.damon.ming.app.config.ai.model_config_client import load_model_config
from src.com.damon.ming.app.config.ai.rag.config import RagConfig, RagConfigLoader
from src.com.damon.ming.app.config.env import (
    get_inference_gateway_url as read_inference_gateway_url,
)


def _merge_model_metadata(
    config: dict[str, Any], model_catalog: dict[str, Any]
) -> dict[str, Any]:
    """按 role 的 model_name 注入 gateway 模型规格。"""
    if not isinstance(config, dict):
        raise TypeError("AI 配置必须是 YAML 对象")
    if not isinstance(model_catalog, dict) or not model_catalog:
        raise ValueError("model-gateway 模型配置为空")

    merged = deepcopy(config)
    roles = merged.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("AI 配置缺少 roles 段")

    for role, role_config in roles.items():
        if not isinstance(role_config, dict):
            raise TypeError(f"roles.{role} 配置必须是映射")
        model_name = role_config.get("model_name")
        model_spec = model_catalog.get(model_name)
        if not isinstance(model_spec, dict):
            raise TypeError(
                f"roles.{role}.model_name 未在 model-gateway 注册: {model_name}"
            )
        max_model_len = model_spec.get("max_model_len")
        if type(max_model_len) is not int or max_model_len < 2:
            raise ValueError(
                f"model-gateway models.{model_name}.max_model_len 配置无效"
            )
        if role_config.get("max_model_len") != "${model.max_model_len}":
            raise ValueError(
                f"roles.{role}.max_model_len 必须声明为 ${{model.max_model_len}}"
            )
        role_config["max_model_len"] = max_model_len
        if "dimension" in role_config:
            if role_config["dimension"] != "${model.dimension}":
                raise ValueError(
                    f"roles.{role}.dimension 必须声明为 ${{model.dimension}}"
                )
            dimension = model_spec.get("dimension")
            if type(dimension) is not int or dimension <= 0:
                raise ValueError(
                    f"model-gateway models.{model_name}.dimension 配置无效"
                )
            role_config["dimension"] = dimension

    return merged


@dataclass(frozen=True)
class AiConfig:
    """启动时装配完成的应用侧 AI 配置。"""

    inference: dict[str, Any]
    embedding: dict[str, Any]
    rag_runtime_config: RagConfig
    rag_module_configs: dict[str, dict[str, Any]]


class AiConfigLoader:
    """统一加载本地 AI YAML，并合并 model-gateway 的模型规格。"""

    def __init__(self, *, model_root_dir: str) -> None:
        self._model_root_dir = model_root_dir
        self._inference_gateway_url: str | None = None

    def get_inference_gateway_url(self) -> str:
        """返回并缓存推理网关地址，配置读取统一由本 loader 管理。"""
        if self._inference_gateway_url is None:
            self._inference_gateway_url = read_inference_gateway_url()
        return self._inference_gateway_url

    def load(self) -> AiConfig:
        rag_loader = RagConfigLoader(
            variables={"model_dir": self._model_root_dir},
            deferred_variables={"model.max_model_len", "model.dimension"},
        )
        model_catalog = load_model_config(self.get_inference_gateway_url())
        rag_module_configs = rag_loader.get_modules_config()
        embedding = rag_module_configs.get("embedding")
        if not isinstance(embedding, dict):
            raise TypeError("RAG 配置缺少有效的 modules.embedding 段")
        merged_embedding = _merge_model_metadata(embedding, model_catalog)
        resolved_modules = deepcopy(rag_module_configs)
        resolved_modules["embedding"] = deepcopy(merged_embedding)

        return AiConfig(
            inference=_merge_model_metadata(
                InferenceConfigLoader().load(),
                model_catalog,
            ),
            embedding=merged_embedding,
            rag_runtime_config=RagConfig.from_mapping(rag_loader.get_rag_config()),
            rag_module_configs=resolved_modules,
        )
