"""读取全局线程 worker 预算，不展开具体线程池。"""

import os
from dataclasses import dataclass

from src.com.damon.ming.utils.yaml_loader import load_yaml


@dataclass(frozen=True)
class ThreadPoolBudget:
    max_total_workers: int
    group_limits: dict[str, int]


class ThreadPoolConfigLoader:
    """读取全局和资源组 worker 上限。"""

    def __init__(self) -> None:
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self) -> ThreadPoolBudget:
        raw = load_yaml(self._config_dir, allow_empty=True)
        if not isinstance(raw, dict):
            raise TypeError("线程池配置必须是键值对")

        total_limit = self._positive_int(
            raw.get("max_total_workers"), "max_total_workers"
        )
        raw_groups = raw.get("groups")
        if not isinstance(raw_groups, dict) or not raw_groups:
            raise TypeError("groups 必须是非空键值对")

        group_limits: dict[str, int] = {}
        for group_name, value in raw_groups.items():
            if not isinstance(group_name, str) or not group_name.strip():
                raise ValueError("线程资源组名称必须是非空字符串")
            group_limits[group_name] = self._positive_int(
                value, f"groups.{group_name}"
            )

        if sum(group_limits.values()) > total_limit:
            raise ValueError(
                f"线程资源组预算总和超过 max_total_workers={total_limit}"
            )

        return ThreadPoolBudget(total_limit, group_limits)

    @staticmethod
    def _positive_int(value: object, path: str) -> int:
        if type(value) is not int or value <= 0:
            raise ValueError(f"{path} 必须是正整数")
        return value
