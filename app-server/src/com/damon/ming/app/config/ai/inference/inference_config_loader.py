"""读取并缓存应用侧 inference YAML，返回原始配置字典。"""

from pathlib import Path
from typing import Any

from src.com.damon.ming.utils.yaml_loader import load_yaml


class InferenceConfigLoader:
    def __init__(self) -> None:
        self._config_dir = Path(__file__).resolve().parent
        self._config: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._config is None:
            self._config = load_yaml(self._config_dir / "inference-config.yaml")
        return self._config
