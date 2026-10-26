推理引擎配置加载器 —— 从 backends.yaml 读取配置。

单一配置文件，引擎选择在 compose 层面通过模板复制完成，代码无需感知引擎类型。

配置格式（backends.yaml）：
  base_url: 网关或直连地址
  default_timeout: 默认超时
  roles:
    {role}:
      api_key: 路由 key（gateway 模式）
      model: 模型名（直连模式）
      temperature / top_p / max_tokens: 业务参数

用法：
  loader = InferenceConfigLoader()      # 不传参
  result = loader.load_all()
  engine, entry = loader.get_engine_for_model("chat")
"""

import os
from dataclasses import dataclass
from typing import Any

import yaml
from src.com.damon.ming.ai.inference import resolve_engine
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
)

_CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backends.yaml")
)


@dataclass(frozen=True)
class ModelEntry:
    """模型层加载结果。"""

    model_name: str
    options: dict[str, Any]
    api_key: str
    engine_type: str


class InferenceConfigLoader:
    """从 backends.yaml 加载推理引擎和模型配置。"""

    def __init__(self):
        self._engine_type: str = ""
        self._engines: dict[str, BaseInferenceService] = {}
        self._models: dict[str, ModelEntry] = {}

    def load_all(self) -> dict:
        """一次性加载引擎和模型配置。"""
        if not os.path.exists(_CONFIG_PATH):
            raise FileNotFoundError(f"配置文件不存在: {_CONFIG_PATH}")

        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        if not cfg or "roles" not in cfg:
            raise ValueError(f"配置格式错误，缺少 roles: {_CONFIG_PATH}")

        self._engine_type = os.environ.get("INFERENCE_SERVER", "ollama")
        base_url = cfg.get("base_url", "")
        timeout = cfg.get("default_timeout", 180)
        impl_cls = resolve_engine(self._engine_type)

        for role, role_cfg in cfg["roles"].items():
            api_key = role_cfg.get("api_key", "")
            model_name = role_cfg.get("model", "")

            # api_key 为空时（如 Ollama），共享引擎
            engine_key = api_key or "__shared__"
            if engine_key not in self._engines:
                params = InferenceParams(
                    base_url=base_url,
                    timeout=timeout,
                    api_key=api_key,
                )
                self._engines[engine_key] = impl_cls(params)

            options = {
                k: v for k, v in role_cfg.items()
                if k not in ("api_key", "model")
            }
            self._models[role] = ModelEntry(
                model_name=model_name,
                options=options,
                api_key=api_key,
                engine_type=self._engine_type,
            )

        return {
            "engines": self._engines,
            "models": self._models,
        }

    def get_engine_for_model(
        self, role: str = "chat"
    ) -> tuple[BaseInferenceService, ModelEntry]:
        """获取引擎实例和指定角色的模型信息。"""
        if not self._models:
            self.load_all()
        entry = self._models[role]
        engine_key = entry.api_key or "__shared__"
        engine = self._engines[engine_key]
        return engine, entry
