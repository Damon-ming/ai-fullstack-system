# app-server/src/com/damon/ming/ai/tokenizer/config.py
import os

import yaml
from src.com.damon.ming.ai.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.ai.tokenizer.tokenizer_factory import TokenizerFactory


class TokenizerConfig:
    """分词器配置加载，与EmbeddingConfig/VectorStoreConfig风格统一"""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "tokenizer-config.yaml")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Tokenizer配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
            self.config = raw_config.get("tokenizer", {})

    def get_default(self) -> dict:
        return self.config.get("default", {})

    def get_backup(self) -> dict:
        return self.config.get("backup", {})

    def create_tokenizer(self, profile: str = "default") -> BaseTokenizer:
        """根据配置剖面创建分词器实例"""

        cfg = self.config.get(profile)
        if not cfg:
            raise ValueError(f"Tokenizer未找到配置剖面: {profile}")

        # 剥离provider，剩余参数传给工厂
        kwargs = {k: v for k, v in cfg.items() if k != "provider"}
        return TokenizerFactory.create(provider=cfg["provider"], **kwargs)
