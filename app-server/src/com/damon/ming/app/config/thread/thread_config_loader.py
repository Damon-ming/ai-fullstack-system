# app-server/src/com/damon/ming/app/config/thread/thread_config_loader.py
"""
线程池配置加载器 —— 从 YAML 文件读取线程池参数。

本模块属于 app/config/thread/ 配置子模块。
pool_manager 通过 ThreadPoolConfigLoader().load() 接收参数，
不感知配置来源。

配置来源：本目录下唯一的 YAML 文件。加载失败时抛出异常（线程池是核心依赖，不做静默降级）。
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
        加载失败时抛出异常（线程池是核心依赖，不做静默降级）。
        """
        raw = self._read_yaml()
        pools = {k: int(v) for k, v in raw.items() if isinstance(v, (int, float))}
        if not pools:
            raise ValueError(f"线程池配置文件为空或格式错误: {self._config_dir}")
        return pools

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)
