# app-server/src/com/damon/ming/ai/config/vector_config_loader.py
"""
向量存储配置加载器 —— 从 YAML 文件读取引擎名称和参数，构造 VectorStoreParams。

本模块属于 ai/config/ 配置层，不属于 vector_db/ 模块。
vector_db/ 模块通过 VectorStoreParams 数据类接收参数，不感知配置来源。

配置来源：
  - 仅从 YAML 文件读取，支持 ${ENV_VAR} 环境变量替换
  - 加载失败直接抛出异常，不做静默降级

支持多剖面（default / production），通过 profile 参数选择。

用法：
  store = VectorConfigLoader().load()                    # 默认剖面
  store = VectorConfigLoader().load(profile="production") # 生产剖面
  store = VectorConfigLoader("path/to/config.yaml").load()
"""

import os

import yaml
from src.com.damon.ming.ai.vector_db import resolve_store
from src.com.damon.ming.ai.vector_db.base_vector_db import (
    BaseVectorStore,
    VectorStoreParams,
)


class VectorConfigLoader:
    """从 YAML 文件加载向量存储配置，返回 BaseVectorStore 实例。

    用法：
        store = VectorConfigLoader().load()
        store = VectorConfigLoader().load(profile="production")
    """

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "vector-config.yaml")
        self._config_path = config_path

    def load(self, profile: str = "default") -> "BaseVectorStore":
        """加载指定剖面的配置，返回 BaseVectorStore 实例。"""
        raw = self._read_yaml(profile)
        params_raw = raw.get("params", {})

        # 构造参数数据类（只取已知字段，其余放入 extra）
        known_fields = {f.name for f in VectorStoreParams.__dataclass_fields__.values()}
        base_kwargs = {k: v for k, v in params_raw.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in params_raw.items() if k not in known_fields}
        params = VectorStoreParams(**base_kwargs, extra=extra_kwargs)

        # 根据引擎名称解析实现类
        engine = raw.get("vector_engine")
        if not engine:
            raise ValueError(
                "配置缺少 vector_engine 字段，例如: chroma / pgvector"
            )
        store_class = resolve_store(engine)

        return store_class(params)

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self, profile: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"向量存储配置文件不存在: {self._config_path}")

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)

        if raw_cfg is None or "vector_store" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'vector_store' 根节点")

        section = raw_cfg["vector_store"]
        params = section.get("params", {})

        # 支持 profiles 多剖面（可选）
        profiles = section.get("profiles")
        if profiles:
            if profile not in profiles:
                raise ValueError(
                    f"未找到剖面 '{profile}'，可用: {list(profiles.keys())}"
                )
            # profile 参数覆盖默认 params
            profile_params = profiles[profile].get("params", {})
            merged = {**params, **profile_params}
            # vector_engine 可在 profile 级别覆盖
            engine = profiles[profile].get(
                "vector_engine", section.get("vector_engine")
            )
            return {"vector_engine": engine, "params": merged}

        return section
