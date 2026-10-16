# app-server/src/com/damon/ming/ai/config/rerank_config_loader.py
"""
重排器配置加载器 —— 从 YAML 读取引擎名称和参数，构造 RerankerParams。

本模块属于 ai/config/ 配置层，不属于 rerank/ 模块。
rerank/ 模块通过 RerankerParams 数据类接收参数，不感知配置来源。

启动时通过 load_all() 一次性加载全部配置实例，避免懒加载导致的响应延迟。

用法：
  loader = RerankerConfigLoader()
  rerankers = loader.load_all()          # dict[str, BaseReranker]
  rerankers["zh_primary"].rerank(...)
"""

import os

import yaml
from src.com.damon.ming.ai.rerank import resolve_reranker
from src.com.damon.ming.ai.rerank.base_reranker import BaseReranker, RerankerParams


class RerankerConfigLoader:
    """从 YAML 文件加载重排器配置，返回 BaseReranker 实例。

    启动时全量加载，所有模型在服务启动阶段初始化完毕。
    """

    _cache: dict[str, object] = {}

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "rerank-config.yaml")
        self._config_path = config_path

    def load_all(self) -> dict[str, BaseReranker]:
        """一次性加载 YAML 中所有配置的重排器实例。

        Returns:
            dict[配置名, BaseReranker 实例]
        """
        if self._cache:
            return self._cache  # type: ignore[return-value]

        for name in self._list_names():
            self._cache[name] = self._build_one(name)
        return self._cache  # type: ignore[return-value]

    def load(self, name: str) -> BaseReranker:
        """加载指定名称的重排器，未缓存则构建。

        Args:
            name: rerankers 下的键名

        Returns:
            BaseReranker 实例
        """
        if name in self._cache:
            return self._cache[name]  # type: ignore[return-value]

        instance = self._build_one(name)
        self._cache[name] = instance
        return instance

    # ---- 私有 -------------------------------------------------------------

    def _list_names(self) -> list[str]:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"重排器配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or "rerankers" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'rerankers' 根节点")
        return list(raw_cfg["rerankers"].keys())

    def _build_one(self, name: str) -> BaseReranker:
        raw = self._read_yaml(name)
        params_raw = raw.get("params", {})

        known_fields = {f.name for f in RerankerParams.__dataclass_fields__.values()}
        base_kwargs = {k: v for k, v in params_raw.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in params_raw.items() if k not in known_fields}
        params = RerankerParams(**base_kwargs, extra=extra_kwargs)

        engine = raw.get("rerank_engine")
        if not engine:
            raise ValueError("配置缺少 rerank_engine 字段")
        reranker_class = resolve_reranker(engine)

        return reranker_class(params)

    def _read_yaml(self, name: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"重排器配置文件不存在: {self._config_path}")

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)

        if raw_cfg is None or "rerankers" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'rerankers' 根节点")

        section = raw_cfg["rerankers"]
        if name not in section:
            raise ValueError(
                f"未找到重排器配置: '{name}'. 可用: {list(section.keys())}"
            )
        return section[name]
