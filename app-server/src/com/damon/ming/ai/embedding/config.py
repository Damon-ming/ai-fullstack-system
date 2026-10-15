# app-server/src/com/damon/ming/ai/embedding/config.py
import os
from typing import Optional

import yaml
from src.com.damon.ming.ai.embedding.BaseEmbeddingService import BaseEmbeddingService


class EmbeddingConfig:
    """从配置文件加载 embedding 配置"""
    
    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            # 自动查找配置文件
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "embedding-config.yaml")
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)["embedding"]
    
    def get_default(self) -> dict:
        return self.config["default"]
    
    def get_backup(self) -> dict:
        return self.config.get("backup", {})
    
    def create_embedder(self, profile: str = "default") -> BaseEmbeddingService:
        """根据配置创建 embedder"""
        from .factory import EmbeddingFactory  # 延迟导入避免循环依赖
        
        config = self.config.get(profile)
        if not config:
            raise ValueError(f"未找到配置: {profile}")
        
        # 过滤掉 provider 字段，其余作为 kwargs
        kwargs = {k: v for k, v in config.items() if k != "provider"}
        
        return EmbeddingFactory.create(
            provider=config["provider"],
            **kwargs
        )
