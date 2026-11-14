# app-server/src/com/damon/ming/app/config/thread/thread_config_loader.py
"""
线程池配置加载器 —— 从 YAML 文件读取线程池参数。

本模块属于 app/config/thread/ 配置子模块。
pool_manager 通过 ThreadPoolConfigLoader().load() 接收参数，
不感知配置来源。

配置来源：本目录下唯一的 YAML 文件。允许留空，供后续通用线程池扩展。
RAG 线程池配置在 rag-runtime.yaml 的 rag.pipeline.thread_pools 中。
"""

import os

from src.com.damon.ming.app.config._yaml import load_yaml


class ThreadPoolConfigLoader:
    """从 YAML 文件加载线程池配置。

    用法：
        cfg = ThreadPoolConfigLoader().load()
    """

    def __init__(self):
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self) -> dict[str, int]:
        """加载线程池配置。

        返回: {"retrieval": 4, "document": 8, "inference": 2, ...}
        未配置返回空字典；已配置但格式错误时抛出异常。
        """
        raw = self._read_yaml()
        return self.parse_pools(raw)

    @staticmethod
    def parse_pools(raw: object) -> dict[str, int]:
        """校验命名线程池配置：名称非空，线程数必须为正整数。"""
        if not isinstance(raw, dict):
            raise ValueError("线程池配置必须是键值对")
        for name, workers in raw.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("线程池名称必须是非空字符串")
            if type(workers) is not int or workers <= 0:
                raise ValueError(f"线程池 {name} 的线程数必须是正整数")
        return dict(raw)

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir, allow_empty=True)
