# app-server/src/com/damon/ming/ai/config/retriever/retriever_config_loader.py
"""
检索器配置加载器 —— 从 YAML 读取 HybridRetriever 构造参数和检索参数。

本模块属于 ai/config/ 配置层，不属于 retriever/ 模块。
retriever/ 模块通过 RetrieverConfig 数据类接收参数，不感知配置来源。

启动时通过 load_all() 一次性加载全部配置实例，避免懒加载导致的响应延迟。

用法：
  loader = RetrieverConfigLoader()
  configs = loader.load_all()          # dict[str, RetrieverConfig]
  configs["primary"].top_k             # 检索时的 top_k
  configs["primary"].dense_weight      # HybridRetriever 构造参数
"""

import os

import yaml


class RetrieverConfig:
    """HybridRetriever 配置参数。

    包含构造参数（dense_weight, sparse_weight, fuse_k）、检索参数
    （top_k, dense_top_k, sparse_top_k, dedup_by_section）和去重调优参数
    （max_section_oversample_multiplier, rrf_oversample_multiplier）。
    """

    __slots__ = (
        "dedup_by_section",
        "dense_top_k",
        "dense_weight",
        "fuse_k",
        "max_section_oversample_multiplier",
        "name",
        "rrf_oversample_multiplier",
        "sparse_top_k",
        "sparse_weight",
        "top_k",
    )

    def __init__(
        self,
        name: str,
        top_k: int,
        dense_top_k: int,
        sparse_top_k: int,
        dedup_by_section: bool,
        dense_weight: float,
        sparse_weight: float,
        fuse_k: int,
        max_section_oversample_multiplier: int = 5,
        rrf_oversample_multiplier: int = 3,
    ):
        self.name = name
        self.top_k = top_k
        self.dense_top_k = dense_top_k
        self.sparse_top_k = sparse_top_k
        self.dedup_by_section = dedup_by_section
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.fuse_k = fuse_k
        self.max_section_oversample_multiplier = max_section_oversample_multiplier
        self.rrf_oversample_multiplier = rrf_oversample_multiplier


class RetrieverConfigLoader:
    """从 YAML 文件加载检索器配置，返回 RetrieverConfig 实例。

    启动时全量加载，所有配置在服务启动阶段初始化完毕。
    """

    _cache: dict[str, RetrieverConfig] = {}

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "retriever-config.yaml")
        self._config_path = config_path

    def load_all(self) -> dict[str, RetrieverConfig]:
        """一次性加载 YAML 中所有配置的检索器实例。

        Returns:
            dict[配置名, RetrieverConfig 实例]
        """
        if self._cache:
            return self._cache

        for name in self._list_names():
            self._cache[name] = self._build_one(name)
        return self._cache

    def load(self, name: str) -> RetrieverConfig:
        """加载指定名称的检索器配置，未缓存则构建。

        Args:
            name: retrievers 下的键名

        Returns:
            RetrieverConfig 实例
        """
        if name in self._cache:
            return self._cache[name]

        config = self._build_one(name)
        self._cache[name] = config
        return config

    # ---- 私有 -------------------------------------------------------------

    def _list_names(self) -> list[str]:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"检索器配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or "retrievers" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'retrievers' 根节点")
        return list(raw_cfg["retrievers"].keys())

    def _build_one(self, name: str) -> RetrieverConfig:
        raw = self._read_yaml(name)
        params = raw.get("params", {})

        try:
            return RetrieverConfig(
                name=name,
                top_k=raw["top_k"],
                dense_top_k=raw["dense_top_k"],
                sparse_top_k=raw["sparse_top_k"],
                dedup_by_section=raw["dedup_by_section"],
                dense_weight=raw["dense_weight"],
                sparse_weight=raw["sparse_weight"],
                fuse_k=raw["fuse_k"],
                max_section_oversample_multiplier=params.get(
                    "max_section_oversample_multiplier", 5
                ),
                rrf_oversample_multiplier=params.get("rrf_oversample_multiplier", 3),
            )
        except KeyError as e:
            raise ValueError(f"检索器配置 '{name}' 缺少必填字段: {e}") from e

    def _read_yaml(self, name: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"检索器配置文件不存在: {self._config_path}")

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)

        if raw_cfg is None or "retrievers" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'retrievers' 根节点")

        section = raw_cfg["retrievers"]
        if name not in section:
            raise ValueError(
                f"未找到检索器配置: '{name}'. 可用: {list(section.keys())}"
            )
        return section[name]
