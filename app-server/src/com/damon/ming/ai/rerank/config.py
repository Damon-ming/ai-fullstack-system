# app-server/src/com/damon/ming/ai/rerank/config.py
import os

import yaml
from src.com.damon.ming.ai.rerank.base_reranker import BaseReranker
from src.com.damon.ming.ai.rerank.factory import RerankerFactory


class RerankerConfig:
    """重排器配置加载，与Embedding/VectorStore/Tokenizer/Summarizer风格统一"""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "rerank-config.yaml")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Reranker配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
            self.config = raw_cfg.get("reranker", {})

    def get_default(self) -> dict:
        return self.config.get("default", {})

    def get_fallback(self) -> dict:
        return self.config.get("fallback", {})

    def create_reranker(self, profile: str = "default") -> BaseReranker:
        cfg = self.config.get(profile)
        if not cfg:
            raise ValueError(f"未找到reranker配置剖面: {profile}")

        # 剥离rerank_type，剩余参数透传给工厂
        kwargs = {k: v for k, v in cfg.items() if k != "rerank_type"}
        return RerankerFactory.create(rerank_type=cfg["rerank_type"], **kwargs)
