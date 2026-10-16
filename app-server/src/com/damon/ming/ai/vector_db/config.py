# app-server/src/com/damon/ming/ai/vector_db/config.py
import os

import yaml
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.ai.vector_db.factory import VectorStoreFactory


class VectorStoreConfig:
    """向量存储配置加载"""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "vector-db-config.yaml")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            self.config = config.get("vector_store", {})

    def create_store(self, profile: str = "default") -> BaseVectorStore:

        config = self.config.get(profile)
        if not config:
            raise ValueError(f"未找到配置: {profile}")

        # 过滤掉 provider 字段
        kwargs = {k: v for k, v in config.items() if k != "provider"}

        return VectorStoreFactory.create(provider=config["provider"], **kwargs)
