# app-server/src/com/damon/ming/ai/rag/summary/config/summary_config_loader.py
"""摘要配置加载器 —— 读取摘要分段策略。"""

import os
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class SummaryConfig:
    """摘要策略参数。"""

    system_prompt_template: str
    context_message_template: str
    context_margin_ratio: float | None
    context_overlap_ratio: float | None


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
        context_margin_ratio = raw_config.get("context_margin_ratio")
        if context_margin_ratio is not None:
            if isinstance(context_margin_ratio, bool) or not isinstance(
                context_margin_ratio, (int, float)
            ):
                raise TypeError("summary.context_margin_ratio 必须是数值或 null")
            if not 0 <= context_margin_ratio < 1:
                raise ValueError("summary.context_margin_ratio 必须大于等于 0 且小于 1")

        context_overlap_ratio = raw_config.get("context_overlap_ratio")
        if context_overlap_ratio is not None:
            if isinstance(context_overlap_ratio, bool) or not isinstance(
                context_overlap_ratio, (int, float)
            ):
                raise TypeError("summary.context_overlap_ratio 必须是数值或 null")
            if not 0 <= context_overlap_ratio < 0.5:
                raise ValueError(
                    "summary.context_overlap_ratio 必须大于等于 0 且小于 0.5"
                )

        context_message_template = raw_config.get("context_message_template")
        if (
            not isinstance(context_message_template, str)
            or not context_message_template.strip()
        ):
            raise ValueError("summary.context_message_template 必须是非空字符串")
        required_context_placeholders = ("{context}", "{content}")
        if any(
            placeholder not in context_message_template
            for placeholder in required_context_placeholders
        ):
            raise ValueError(
                "summary.context_message_template 必须包含 {context} 和 {content}"
            )

        system_prompt_template = raw_config.get("system_prompt_template")
        if (
            not isinstance(system_prompt_template, str)
            or not system_prompt_template.strip()
        ):
            raise ValueError("summary.system_prompt_template 必须是非空字符串")
        required_placeholders = ("{max_tokens}",)
        if any(
            placeholder not in system_prompt_template
            for placeholder in required_placeholders
        ):
            raise ValueError("summary.system_prompt_template 必须包含 {max_tokens}")

        self._config = SummaryConfig(
            system_prompt_template=system_prompt_template,
            context_message_template=context_message_template,
            context_margin_ratio=(
                float(context_margin_ratio)
                if context_margin_ratio is not None
                else None
            ),
            context_overlap_ratio=(
                float(context_overlap_ratio)
                if context_overlap_ratio is not None
                else None
            ),
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
