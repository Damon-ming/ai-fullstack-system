# app-server/src/com/damon/ming/ai/rag/embedding/config/embedding_config_loader.py
"""
Embedding 配置加载器 —— 从 YAML 读取引擎参数，构造 EmbeddingParams。

本模块属于 embedding/ 配置层。
embedding/ 实现通过 EmbeddingParams 数据类接收参数。

启动时通过 load_all() 一次性加载全部配置实例，避免懒加载导致的响应延迟。

用法：
  loader = EmbeddingConfigLoader()
  embedders = loader.load_all()      # dict[str, BaseEmbeddingService]
  embedders["ollama"].embed_query(...)
"""

import os

from src.com.damon.ming.ai.rag.embedding import resolve_embedding
from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
    EmbeddingParams,
)
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class EmbeddingConfigLoader:
    """从 YAML 文件加载 embedding 配置，返回 BaseEmbeddingService 实例。

    启动时全量加载，所有模型在服务启动阶段初始化完毕。
    """

    _cache: dict[str, object] = {}

    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )

    def load_all(self) -> dict[str, BaseEmbeddingService]:
        """一次性加载 YAML 中所有配置的 embedding 实例。

        Returns:
            dict[配置名, BaseEmbeddingService 实例]
        """
        if self._cache:
            return self._cache  # type: ignore[return-value]

        for name in self._list_names():
            self._cache[name] = self._build_one(name)
        return self._cache  # type: ignore[return-value]

    def load(self, engine: str) -> BaseEmbeddingService:
        """加载指定引擎的 embedding 实例，未缓存则构建。

        Args:
            engine: 引擎名称，如 "ollama" / "huggingface"

        Returns:
            BaseEmbeddingService 实例
        """
        if engine in self._cache:
            return self._cache[engine]  # type: ignore[return-value]

        instance = self._build_one(engine)
        self._cache[engine] = instance
        return instance

    # ---- 私有 -------------------------------------------------------------

    def _list_names(self) -> list[str]:
        raw_cfg = load_yaml(self._config_path)
        if raw_cfg is None or "embedding_engines" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'embedding_engines' 根节点")
        return list(raw_cfg["embedding_engines"].keys())

    def _build_one(self, engine: str) -> BaseEmbeddingService:
        raw = self._read_yaml(engine)
        params_raw = raw.get("params", {})

        known_fields = {f.name for f in EmbeddingParams.__dataclass_fields__.values()}
        base_kwargs = {k: v for k, v in params_raw.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in params_raw.items() if k not in known_fields}
        params = EmbeddingParams(**base_kwargs, extra=extra_kwargs)

        embed_class = resolve_embedding(engine)
        return embed_class(params)

    def _read_yaml(self, engine: str) -> dict:
        raw_cfg = load_yaml(self._config_path)

        if raw_cfg is None or "embedding_engines" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'embedding_engines' 根节点")

        section = raw_cfg["embedding_engines"]
        if engine not in section:
            raise ValueError(
                f"未找到引擎配置: '{engine}'. 可用: {list(section.keys())}"
            )

        return section[engine]
