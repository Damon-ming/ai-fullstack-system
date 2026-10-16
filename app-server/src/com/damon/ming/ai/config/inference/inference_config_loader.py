# app-server/src/com/damon/ming/ai/config/inference/inference_config_loader.py
"""
推理引擎配置加载器 —— 从 YAML 读取引擎和模型配置，构造 InferenceParams。

本模块属于 config/inference/ 配置层，不属于 inference/ 模块。
inference/ 模块通过 InferenceParams 数据类接收参数，不感知配置来源。

两层结构：
  - engine：推理后端基础设施（连接参数），type 映射到 @register_engine
  - models：按业务用途命名，数组格式，继承上层 engine

启动时全量加载，所有引擎和模型在服务启动阶段初始化完毕。

用法：
  loader = InferenceConfigLoader()
  result = loader.load_all()
  result["engine"]             # BaseInferenceService
  result["models"]             # dict[模型用途名, ModelEntry]

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


@dataclass(frozen=True)
class ModelEntry:
    """模型层加载结果。"""

    model_name: str
    options: dict[str, Any]  # 模型级推理参数（temperature / top_p / num_ctx）
    engine_type: str  # 继承自上层 engine.type


class InferenceConfigLoader:
    """从 YAML 加载推理引擎和模型配置。"""

    _engine: BaseInferenceService | None = None
    _engine_type: str = ""
    _models: dict[str, ModelEntry] = {}

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "inference-config.yaml")
        self._config_path = config_path

    def load_all(self) -> dict:
        """一次性加载引擎和模型配置。

        Returns:
            {
                "engine": BaseInferenceService,
                "models": dict[模型用途名, ModelEntry],
            }
        """
        if self._engine is not None:
            return {
                "engine": self._engine,
                "models": self._models,
            }

        raw_cfg = self._read_yaml()

        # 1. 加载引擎层
        engine_cfg = raw_cfg.get("engine", {})
        self._engine_type = engine_cfg.get("type", "")

        params = InferenceParams(
            base_url=engine_cfg["base_url"],
            timeout=engine_cfg["timeout"],
            max_retries=engine_cfg["max_retries"],
            api_key=engine_cfg.get("api_key", ""),
        )

        impl_cls = resolve_engine(self._engine_type)
        self._engine = impl_cls(params)

        # 2. 加载模型层 —— 统一数组格式，继承上层 engine
        for model_role, model_cfg in raw_cfg.get("models", {}).items():
            if not isinstance(model_cfg, list):
                raise ValueError(
                    f"模型 '{model_role}' 配置格式错误：期望数组，"
                    f"实际为 {type(model_cfg).__name__}"
                )
            if not model_cfg:
                raise ValueError(f"模型 '{model_role}' 配置为空数组")

            primary = model_cfg[0]
            entry = ModelEntry(
                model_name=primary["model_name"],
                options={k: v for k, v in primary.items() if k != "model_name"},
                engine_type=self._engine_type,
            )
            self._models[model_role] = entry

        return {
            "engine": self._engine,
            "models": self._models,
        }

    def get_engine_for_model(
        self, role: str = "chat"
    ) -> tuple[BaseInferenceService, ModelEntry]:
        """获取引擎实例和指定用途的模型信息。

        Returns:
            (engine, ModelEntry)
        """
        if self._engine is None:
            self.load_all()
        entry = self._models[role]
        return self._engine, entry

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"推理配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or "engine" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'engine' 根节点")
        return raw_cfg
