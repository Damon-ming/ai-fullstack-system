# app-server/src/com/damon/ming/app/config/thread/thread_config_loader.py
"""
线程池配置加载器 —— 从 YAML 文件读取线程池参数。

本模块属于 app/config/thread/ 配置子模块。
pool_manager 通过 ThreadPoolConfigLoader().load() 接收参数，
不感知配置来源。

配置来源：本目录下唯一的 YAML 文件。校验全局和分组 worker 上限，加载后展平为线程池名称和 worker 数量。
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

        返回管理器所需的平面配置，例如 {"retrieval": 4, "database_query": 2}。
        """
        raw = self._read_yaml()
        if not isinstance(raw, dict):
            raise TypeError("thread_pools 配置必须是键值对")
        config = raw.get("thread_pools")
        if not isinstance(config, dict):
            raise TypeError("thread_pools 必须是键值对")
        total_limit = self._positive_int(
            config.get("max_total_workers"), "thread_pools.max_total_workers"
        )
        groups = config.get("groups")
        if not isinstance(groups, dict) or not groups:
            raise TypeError("thread_pools.groups 必须是非空键值对")
        pools: dict[str, int] = {}
        configured_group_limits = 0
        for group_name, group in groups.items():
            if not isinstance(group_name, str) or not group_name.strip():
                raise ValueError("线程池分组名称必须是非空字符串")
            if not isinstance(group, dict):
                raise TypeError(f"线程池分组 {group_name} 必须是键值对")
            group_limit = self._positive_int(
                group.get("max_total_workers"),
                f"thread_pools.groups.{group_name}.max_total_workers",
            )
            configured_group_limits += group_limit
            group_pools = group.get("pools")
            if not isinstance(group_pools, dict) or not group_pools:
                raise TypeError(f"线程池分组 {group_name}.pools 必须是非空键值对")
            group_total = 0
            for pool_name, pool_config in group_pools.items():
                if not isinstance(pool_name, str) or not pool_name.strip():
                    raise ValueError("线程池名称必须是非空字符串")
                if not isinstance(pool_config, dict):
                    raise TypeError(f"线程池 {group_name}.{pool_name} 必须是键值对")
                workers = self._positive_int(
                    pool_config.get("max_workers"),
                    f"thread_pools.groups.{group_name}.pools.{pool_name}.max_workers",
                )
                name = f"{group_name}_{pool_name}"
                if name in pools:
                    raise ValueError(f"线程池名称重复：{name}")
                pools[name] = workers
                group_total += workers
            if group_total > group_limit:
                raise ValueError(
                    f"线程池分组 {group_name} 的 worker 总数 {group_total} "
                    f"超过 max_total_workers={group_limit}"
                )
        if configured_group_limits > total_limit:
            raise ValueError(
                f"分组 max_total_workers 总和 {configured_group_limits} "
                f"超过 thread_pools.max_total_workers={total_limit}"
            )
        return pools

    @staticmethod
    def _positive_int(value: object, path: str) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError(f"{path} 必须是正整数")
        return value

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir, allow_empty=True)
