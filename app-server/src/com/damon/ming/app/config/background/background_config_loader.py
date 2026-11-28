"""从 YAML 加载周期后台任务调度配置。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from src.com.damon.ming.utils.yaml_loader import load_yaml


@dataclass(frozen=True)
class BackgroundTaskConfig:
    startup_delay_seconds: float
    interval_seconds: float
    batch_size: int


class BackgroundTaskConfigLoader:
    def load(self) -> BackgroundTaskConfig:
        config = load_yaml(Path(__file__).resolve().parent)

        startup_delay = self._seconds(
            config.get("startup_delay_seconds"),
            "startup_delay_seconds",
            allow_zero=True,
        )
        interval = self._seconds(
            config.get("interval_seconds"),
            "interval_seconds",
        )
        batch_size = config.get("batch_size")
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size 必须是正整数")
        return BackgroundTaskConfig(startup_delay, interval, batch_size)

    @staticmethod
    def _seconds(value: object, path: str, *, allow_zero: bool = False) -> float:
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value < 0
            or (value == 0 and not allow_zero)
        ):
            requirement = "大于等于 0" if allow_zero else "大于 0"
            raise ValueError(f"{path} 必须是{requirement}的有限数字")
        return float(value)
