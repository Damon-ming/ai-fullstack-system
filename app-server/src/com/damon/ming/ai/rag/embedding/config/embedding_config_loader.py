# app-server/src/com/damon/ming/ai/rag/embedding/config/embedding_config_loader.py
"""
Embedding 配置加载器 —— 从 YAML 读取引擎参数，构造 EmbeddingParams。

本模块属于 embedding/ 配置层。
embedding/ 实现通过 EmbeddingParams 数据类接收参数。

RagTool 选择引擎后，本加载器合并 common 与对应引擎配置并构造一个实例。

用法：
  loader = EmbeddingConfigLoader()
  embedder = loader.load(EmbeddingEngine.HUGGINGFACE)
  embedder.embed_query(...)
"""

import os

from src.com.damon.ming.ai.rag.embedding import resolve_embedding
from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.ai.rag.embedding.embedding_engine import EmbeddingEngine
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class EmbeddingConfigLoader:
    """从 YAML 文件加载 embedding 配置，返回 BaseEmbeddingService 实例。

    仅初始化调用方选定的引擎。
    """

    _cache: dict[str, object] = {}

    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )

    def load(self, engine: EmbeddingEngine) -> BaseEmbeddingService:
        """加载指定引擎的 embedding 实例，未缓存则构建。

        Args:
            engine: 上层选择的 embedding 引擎。

        Returns:
            BaseEmbeddingService 实例
        """
        engine_name = engine.value
        if engine_name in self._cache:
            return self._cache[engine_name]  # type: ignore[return-value]

        instance = self._build_one(engine_name)
        self._cache[engine_name] = instance
        return instance

    # ---- 私有 -------------------------------------------------------------

    def _build_one(self, engine: str) -> BaseEmbeddingService:
        raw = self._read_yaml(engine)
        model_name = raw.pop("model_name", None)
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError(f"Embedding 引擎 {engine} 缺少有效的 model_name")
        params = EmbeddingParams(model_name=model_name, extra=raw)

        embed_class = resolve_embedding(engine)
        return embed_class(params)

    def _read_yaml(self, engine: str) -> dict:
        raw_cfg = load_yaml(self._config_path)

        if not isinstance(raw_cfg, dict):
            raise ValueError("Embedding 配置必须是 YAML 对象")
        if engine not in raw_cfg:
            raise ValueError(
                f"未找到引擎配置: '{engine}'. 可用: {list(raw_cfg.keys())}"
            )

        common = raw_cfg.get("common", {})
        engine_config = raw_cfg[engine]
        if not isinstance(common, dict) or not isinstance(engine_config, dict):
            raise TypeError("Embedding common 和引擎配置必须是 YAML 对象")
        model_config = engine_config.get("model_config")
        if not isinstance(model_config, dict):
            raise ValueError(f"Embedding 引擎 {engine} 缺少 model_config")
        return {**common, **model_config}
