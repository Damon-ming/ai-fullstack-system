# app-server/src/com/damon/ming/ai/intent/intention_config.py
import os

import yaml
from src.com.damon.ming.ai.intent.base_intention import BaseIntentionClassifier
from src.com.damon.ming.ai.intent.intention_factory import IntentionFactory


class IntentionConfig:
    """意图识别配置加载，风格与SummarizerConfig统一"""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "intention-config.yaml")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"意图识别配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
            self.config = raw_cfg.get("intention", {})

    def get_default(self) -> dict:
        return self.config.get("default", {})

    def get_fallback(self) -> dict:
        return self.config.get("fallback", {})

    def create_classifier(self, profile: str = "default") -> BaseIntentionClassifier:
        """根据配置剖面生成意图识别实例"""
        cfg = self.config.get(profile)
        if not cfg:
            raise ValueError(f"未找到意图配置剖面: {profile}")

        kwargs = {k: v for k, v in cfg.items() if k != "provider"}
        return IntentionFactory.create(provider=cfg["provider"], **kwargs)
