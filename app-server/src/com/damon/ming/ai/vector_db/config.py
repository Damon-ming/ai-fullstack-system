# app-server/src/com/damon/ming/ai/vector_db/config.py
"""向量存储配置加载 —— 纯 YAML 读取，不含数据库连接逻辑。"""
import os

import yaml
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.ai.vector_db.factory import VectorStoreFactory


class VectorStoreConfig:
    """向量存储配置加载（仅负责 YAML 解析和工厂调度）。

    数据库连接由外层（rag_tool）通过 create_store 的 db_connection 参数注入，
    本类不感知 DbConnection / DbConfig。
    """

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "vector-db-config.yaml")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            self.config = config.get("vector_store", {})

    def create_store(
        self,
        profile: str = "default",
        db_connection=None,
    ) -> BaseVectorStore:
        """创建向量存储实例。

        参数：
            profile: YAML 中的配置剖面名
            db_connection: 外部注入的数据库连接（pgvector 需要，chromadb 传 None）
        """
        config = self.config.get(profile)
        if not config:
            raise ValueError(f"未找到配置: {profile}")

        provider = config["provider"]
        kwargs = {k: v for k, v in config.items() if k != "provider"}

        # pgvector 需要外部注入 db_connection
        if provider == "pgvector":
            if db_connection is None:
                raise ValueError(
                    "pgvector 需要外部注入 db_connection。"
                    "请在调用 create_store 前创建 DbConnection 并传入。"
                )
            kwargs["db_connection"] = db_connection
            # connection_string 已由外层处理，不再需要
            kwargs.pop("connection_string", None)

        return VectorStoreFactory.create(provider=provider, **kwargs)
