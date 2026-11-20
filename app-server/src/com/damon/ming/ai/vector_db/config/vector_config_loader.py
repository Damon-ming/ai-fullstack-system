# app-server/src/com/damon/ming/ai/vector_db/config/vector_config_loader.py
"""
向量存储配置加载器 —— 从 YAML 读取引擎参数，构造 VectorStoreParams。

本模块属于 ai/vector_db/config/ 配置层，不属于 vector_db/ 模块。
vector_db/ 模块通过 VectorStoreParams 数据类接收参数，不感知配置来源。

上层调用方必须显式指定引擎名，不能依赖隐式默认值。

用法：
  store = VectorConfigLoader().load("chroma")
  store = VectorConfigLoader().load("pgvector")
"""

import os

import yaml
from src.com.damon.ming.ai.vector_db import resolve_store
from src.com.damon.ming.ai.vector_db.base_vector_db import (
    BaseVectorStore,
    ChromaParams,
    PGVectorParams,
    SharedVectorStoreParams,
    VectorStoreParams,
)


class VectorConfigLoader:
    """从 YAML 文件加载向量存储配置，返回 BaseVectorStore 实例。

    必须显式指定引擎名，同名实例缓存复用。
    """

    _cache: dict[str, BaseVectorStore] = {}

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "vector-config.yaml")
        self._config_path = config_path

    def load(self, engine: str) -> "BaseVectorStore":
        """加载指定引擎的向量存储配置，返回实例。

        Args:
            engine: 引擎名称，如 "chroma" / "pgvector"

        Returns:
            BaseVectorStore 实例
        """
        if engine in self._cache:
            return self._cache[engine]

        raw = self._read_yaml(engine)
        if not isinstance(raw, dict):
            raise TypeError(f"引擎 '{engine}' 配置必须是键值对")
        raw_params = dict(raw)
        try:
            shared_params = SharedVectorStoreParams(
                table_name=raw_params.pop("table_name"),
                embedding_dimension=raw_params.pop("embedding_dimension"),
            )
        except KeyError as exc:
            raise ValueError(
                f"引擎 '{engine}' 配置缺少公共参数: {exc.args[0]}"
            ) from exc

        engine_params_types = {
            "pgvector": PGVectorParams,
            "chroma": ChromaParams,
        }
        try:
            engine_params_type = engine_params_types[engine]
        except KeyError as exc:
            raise ValueError(f"没有引擎参数类型定义: '{engine}'") from exc
        try:
            engine_params = engine_params_type(**raw_params)
        except TypeError as exc:
            raise ValueError(f"引擎 '{engine}' 配置字段无效: {exc}") from exc

        params = VectorStoreParams(
            shared_params=shared_params,
            engine_params=engine_params,
        )

        store_class = resolve_store(engine)
        instance = store_class(params)
        self._cache[engine] = instance
        return instance

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self, engine: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"向量存储配置文件不存在: {self._config_path}")

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)

        if raw_cfg is None or not isinstance(raw_cfg, dict):
            raise ValueError("配置文件格式错误：顶层必须是键值对")

        if engine not in raw_cfg:
            raise ValueError(
                f"未找到引擎配置: '{engine}'. 可用: {list(raw_cfg.keys())}"
            )

        return raw_cfg[engine]
