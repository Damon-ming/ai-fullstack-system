# app-server/src/com/damon/ming/ai/rag/summary/config/summary_config_loader.py
"""摘要配置加载器 —— 读取摘要分段策略。"""

import math
import os
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class SummaryConfig:
    """摘要策略参数。"""

    input_max_ratio: float
    prompt_template: str


class SummaryConfigLoader:
    """从 YAML 加载摘要策略配置。"""

    def __init__(self, config_path: str | None = None):
        self._config: SummaryConfig | None = None
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "summary-config.yaml")
        self._config_path = config_path

    def load(self) -> SummaryConfig:
        if self._config is not None:
            return self._config

        raw_config = self._read_yaml()
        value = raw_config.get("input_max_ratio")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("summary.input_max_ratio 必须大于 0 且小于 1")
        ratio = float(value)
        if not math.isfinite(ratio) or not 0 < ratio < 1:
            raise ValueError("summary.input_max_ratio 必须大于 0 且小于 1")

        prompt_template = raw_config.get("prompt_template")
        if not isinstance(prompt_template, str) or not prompt_template.strip():
            raise ValueError("summary.prompt_template 必须是非空字符串")
        required_placeholders = ("{max_tokens}", "{content}")
        if any(
            placeholder not in prompt_template for placeholder in required_placeholders
        ):
            raise ValueError(
                "summary.prompt_template 必须包含 {max_tokens} 和 {content}"
            )

        self._config = SummaryConfig(
            input_max_ratio=ratio,
            prompt_template=prompt_template,
        )
        return self._config

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"摘要配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)

        if not isinstance(raw_config, dict):
            raise TypeError("摘要配置文件格式错误：需要顶层键值对")
        return raw_config
