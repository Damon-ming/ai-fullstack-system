"""读取 AI 资源组内部的线程池分配。"""

import os

from src.com.damon.ming.app.config._yaml import load_yaml


class AiThreadPoolConfigLoader:
    def __init__(self) -> None:
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self) -> dict[str, int]:
        raw = load_yaml(self._config_dir, allow_empty=True)
        if not isinstance(raw, dict) or not raw:
            raise TypeError("AI 线程池配置必须是非空键值对")

        result: dict[str, int] = {}
        for name, workers in raw.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("AI 线程池名称必须是非空字符串")
            if type(workers) is not int or workers <= 0:
                raise ValueError(f"AI 线程池 {name} 的 worker 数必须是正整数")
            result[name] = workers
        return result
