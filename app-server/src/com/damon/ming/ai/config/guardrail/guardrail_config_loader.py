# app-server/src/com/damon/ming/ai/config/guardrail/guardrail_config_loader.py
"""
护栏配置加载器 —— 从 YAML 读取护栏配置，构造 GuardrailParams。

本模块属于 config/guardrail/ 配置层，不属于 guardrail/ 模块。
guardrail/ 模块通过 GuardrailParams 数据类接收参数，不感知配置来源。

护栏引擎复用已初始化的推理引擎，初始化时通过参数注入。

启动时全量加载，护栏引擎在服务启动阶段初始化完毕。

用法：
  loader = GuardrailConfigLoader()
  result = loader.load_all(inference=infer_service)
  result["engine"]  # BaseGuardrail
"""

import os

import yaml
from src.com.damon.ming.ai.guardrail import resolve_guardrail
from src.com.damon.ming.ai.guardrail.base_guardrail import (
    BaseGuardrail,
    GuardrailParams,
)
from src.com.damon.ming.ai.inference.base_inference import BaseInferenceService


class GuardrailConfigLoader:
    """从 YAML 加载护栏配置。"""

    def __init__(self, config_path: str | None = None):
        self._engine: BaseGuardrail | None = None
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "guardrail-config.yaml")
        self._config_path = config_path

    def load_all(self, inference: BaseInferenceService) -> dict:
        """一次性加载护栏配置。

        Args:
            inference: 已初始化的推理引擎实例，注入到护栏引擎中复用。

        Returns:
            {"engine": BaseGuardrail}
        """
        if self._engine is not None:
            return {"engine": self._engine}

        raw_cfg = self._read_yaml()
        engine_cfg = raw_cfg.get("engine", {})

        params = GuardrailParams(
            model_name=engine_cfg["model_name"],
            prompt_template=engine_cfg["prompt_template"],
        )

        impl_cls = resolve_guardrail(engine_cfg["type"])
        self._engine = impl_cls(params, inference=inference)

        return {"engine": self._engine}

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"护栏配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or "engine" not in raw_cfg:
            raise ValueError("护栏配置文件格式错误：缺少 'engine' 根节点")
        return raw_cfg
