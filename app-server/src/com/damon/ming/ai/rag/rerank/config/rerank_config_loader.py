# app-server/src/com/damon/ming/ai/rag/rerank/config/rerank_config_loader.py
"""
重排器配置加载器 —— 从 YAML 读取模型参数并构造唯一的 Reranker。

本模块属于 rerank/ 配置层。
rerank/ 模块通过 RerankerParams 数据类接收参数，不感知配置来源。

启动时一次性加载模型，避免懒加载导致的响应延迟。

用法：
  loader = RerankerConfigLoader()
  reranker = loader.load("bge_reranker_v2_m3", model_root_dir)
  reranker.rerank(...)
"""

import os
from pathlib import Path

from src.com.damon.ming.ai.rag.rerank import resolve_reranker
from src.com.damon.ming.ai.rag.rerank.base_reranker import BaseReranker, RerankerParams
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class RerankerConfigLoader:
    """从 YAML 文件加载重排器配置，返回 BaseReranker 实例。

    当前项目使用 CrossEncoder 引擎；按 YAML 顶层实例名加载模型参数。
    """

    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )
        self._rerankers: dict[str, BaseReranker] = {}

    def load(self, name: str, model_root_dir: Path) -> BaseReranker:
        """按 YAML 顶层实例名加载重排器。"""
        if name in self._rerankers:
            return self._rerankers[name]

        raw_config = load_yaml(self._config_path)
        if not isinstance(raw_config, dict):
            raise ValueError("重排器配置文件必须是键值对象")
        if name not in raw_config:
            raise ValueError(
                f"未找到重排器配置: '{name}'. 可用: {list(raw_config.keys())}"
            )
        config = raw_config[name]
        if not isinstance(config, dict):
            raise TypeError(f"重排器配置 '{name}' 必须是键值对象")

        model_name = config.get("model_name")
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("重排器配置缺少有效的 model_name")

        model_path = Path(model_name)
        if not model_path.is_absolute():
            config["model_name"] = str(model_root_dir / "rerank" / model_path)

        known_fields = {f.name for f in RerankerParams.__dataclass_fields__.values()}
        base_kwargs = {k: v for k, v in config.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in config.items() if k not in known_fields}
        params = RerankerParams(**base_kwargs, extra=extra_kwargs)

        # 当前只实现并使用 CrossEncoder；引擎选择固定在代码中，不作为 YAML 参数。
        reranker_class = resolve_reranker("cross_encoder")
        reranker = reranker_class(params)
        self._rerankers[name] = reranker
        return reranker
