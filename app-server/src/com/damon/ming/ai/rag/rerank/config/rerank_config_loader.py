# app-server/src/com/damon/ming/ai/rag/rerank/config/rerank_config_loader.py
"""
重排器配置加载器 —— 从 YAML 读取并校验模型参数。

本模块属于 rerank/ 配置层。
返回 RerankerParams，不负责解析模型路径或实例化模型。

用法：
  loader = RerankerConfigLoader()
  params = loader.load("bge_reranker_v2_m3")
"""

import os

from src.com.damon.ming.ai.rag.rerank.base_reranker import RerankerParams
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class RerankerConfigLoader:
    """从 YAML 文件按模型配置名加载 RerankerParams。"""

    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )

    def load(self, name: str) -> RerankerParams:
        """按 YAML 顶层模型配置名读取参数。"""
        raw_config = load_yaml(self._config_path)
        if not isinstance(raw_config, dict):
            raise TypeError("重排器配置文件必须是键值对象")
        if name not in raw_config:
            raise ValueError(
                f"未找到重排器配置: '{name}'. 可用: {list(raw_config.keys())}"
            )
        config = raw_config[name]
        if not isinstance(config, dict):
            raise TypeError(f"重排器配置 '{name}' 必须是键值对象")

        known_fields = {f.name for f in RerankerParams.__dataclass_fields__.values()}
        base_kwargs = {k: v for k, v in config.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in config.items() if k not in known_fields}
        return RerankerParams(**base_kwargs, extra=extra_kwargs)
