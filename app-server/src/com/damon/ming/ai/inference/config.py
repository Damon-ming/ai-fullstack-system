# app-server/src/com/damon/ming/ai/inference/config.py
import os

import yaml
from src.com.damon.ming.ai.inference.base_inference import BaseInferenceService
from src.com.damon.ming.ai.inference.factory import InferenceFactory


class InferenceConfig:
    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "inference-config.yaml")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"推理配置文件不存在: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
            self.config = raw_cfg.get("inference", {})

    def get_default(self) -> dict:
        return self.config.get("default", {})

    def get_fallback(self) -> dict:
        return self.config.get("fallback", {})

    def get_profile_cfg(self, profile: str = "default") -> dict:
        """获取指定剖面完整配置"""
        cfg = self.config.get(profile)
        if not cfg:
            raise ValueError(f"未找到推理配置剖面 {profile}")
        return cfg

    def get_llm_model_name(self, profile: str = "default") -> str:
        """获取问答主模型名称"""
        cfg = self.get_profile_cfg(profile)
        return cfg.get("llm_model", "qwen:1.8b")

    def create_infer_client(self, profile: str = "default") -> BaseInferenceService:
        cfg = self.get_profile_cfg(profile)
        kwargs = {k: v for k, v in cfg.items() if k not in ("provider", "llm_model")}
        return InferenceFactory.create(provider=cfg["provider"], **kwargs)
