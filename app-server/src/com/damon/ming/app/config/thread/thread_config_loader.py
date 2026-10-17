# app-server/src/com/damon/ming/app/config/thread/thread_config_loader.py
"""
线程池配置加载器 —— 从 YAML 文件读取线程池参数。

本模块属于 app/config/thread/ 配置子模块。
pool_manager 通过 ThreadPoolConfigLoader().load() 接收参数，
不感知配置来源。

加载优先级：
  1. 显式传入的 config_path
  2. THREAD_CONFIG_PATH 环境变量
  3. 默认路径：本目录下的 thread-config.yaml

加载失败时抛出异常（线程池是核心依赖，不做静默降级）。
"""

import os

import yaml


class ThreadPoolConfigLoader:
    """从 YAML 文件加载线程池配置。

    用法：
        cfg = ThreadPoolConfigLoader().load()
        cfg = ThreadPoolConfigLoader("path/to/config.yaml").load()
    """

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = os.environ.get("THREAD_CONFIG_PATH", "")
        if not config_path:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "thread-config.yaml")
        self._config_path = config_path

    def load(self) -> dict[str, int]:
        """加载线程池配置。

        返回: {"retrieval": 4, "document": 8, "inference": 2, ...}
        加载失败时抛出异常（线程池是核心依赖，不做静默降级）。
        """
        raw = self._read_yaml()
        pools = {k: int(v) for k, v in raw.items() if isinstance(v, (int, float))}
        if not pools:
            raise ValueError(f"线程池配置文件为空或格式错误: {self._config_path}")
        return pools

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"线程池配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if not raw_cfg or not isinstance(raw_cfg, dict):
            raise ValueError("线程池配置文件格式错误：需要顶层键值对")
        return raw_cfg
