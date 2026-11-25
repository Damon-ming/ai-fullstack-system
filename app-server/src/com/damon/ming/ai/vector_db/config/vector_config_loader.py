# app-server/src/com/damon/ming/ai/vector_db/config/vector_config_loader.py
"""从 YAML 加载并校验静态向量存储配置。"""

import os
from dataclasses import dataclass

from src.com.damon.ming.ai.vector_db.base_vector_db import (
    ChromaParams,
    PGVectorParams,
)
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


@dataclass(frozen=True)
class LoadedVectorStoreConfig:
    """从 YAML 解析出的静态向量存储配置。"""

    engine: str
    table_name: str
    engine_params: PGVectorParams | ChromaParams


class VectorConfigLoader:
    """只从 YAML 文件加载并校验静态向量存储配置。"""

    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )

    def load(self, engine: str) -> LoadedVectorStoreConfig:
        """加载指定引擎的 YAML 配置，不创建向量存储实例。

        Args:
            engine: 引擎名称，如 "chroma" / "pgvector"

        Returns:
            已校验的静态向量存储配置。
        """
        raw = self._read_yaml(engine)
        if not isinstance(raw, dict):
            raise TypeError(f"引擎 '{engine}' 配置必须是键值对")
        raw_params = dict(raw)
        try:
            table_name = raw_params.pop("table_name")
        except KeyError as exc:
            raise ValueError(
                f"引擎 '{engine}' 配置缺少公共参数: {exc.args[0]}"
            ) from exc
        if not isinstance(table_name, str) or not table_name.strip():
            raise ValueError(f"引擎 '{engine}' 的 table_name 必须是非空字符串")

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

        return LoadedVectorStoreConfig(
            engine=engine,
            table_name=table_name,
            engine_params=engine_params,
        )

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self, engine: str) -> dict:
        raw_cfg = load_yaml(self._config_path)

        if raw_cfg is None or not isinstance(raw_cfg, dict):
            raise ValueError("配置文件格式错误：顶层必须是键值对")

        if engine not in raw_cfg:
            raise ValueError(
                f"未找到引擎配置: '{engine}'. 可用: {list(raw_cfg.keys())}"
            )

        return raw_cfg[engine]
