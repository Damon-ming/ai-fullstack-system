# app-server/src/com/damon/ming/app/config/rag/rag_runtime_config_loader.py
# RAG 运行时配置加载器 —— 流程配置和多语言文本。

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.app.config._yaml import load_yaml
from src.com.damon.ming.app.config.i18n.i18n_config_loader import I18nConfigLoader

# ═══════════════════════════════════════════════════════════════════════
# 数据类 —— 与 rag-runtime.yaml 的段落一一对应
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LocaleConfig:
    """rag.locales.{locale} 段 —— 单个 locale 的聊天文本。"""

    ref_label: str
    query_label: str
    system_prompt: str
    guardrail_prompt_template: str


@dataclass(frozen=True)
class RagConfig:
    """rag 段。"""

    execution_timeout_seconds: float  # 检索、上下文构造和主推理预算（秒），不含护栏
    rag_max_concurrency: int
    retry_ms: int
    locales: dict[str, LocaleConfig]


@dataclass(frozen=True)
class RagRuntimeConfig:
    """rag-runtime.yaml 的直接映射。

    rag —— 流程并发、超时和 locales 文本。
    """

    rag: RagConfig


# ═══════════════════════════════════════════════════════════════════════
# 加载器
# ═══════════════════════════════════════════════════════════════════════


class RagConfigLoader:
    """RAG 运行时配置加载器。

    load() 只执行一次，重复调用直接返回缓存结果。
    """

    def __init__(self) -> None:
        self._config_dir: str = os.path.dirname(os.path.abspath(__file__))
        self._config: RagRuntimeConfig | None = None

    def load(self) -> RagRuntimeConfig:
        """加载 rag-runtime.yaml，并缓存配置结果。"""
        if self._config is not None:
            return self._config

        raw = self._read_yaml()
        self._config = RagRuntimeConfig(
            rag=self._load_rag(raw),
        )
        return self._config

    # ---- 私有：YAML 段映射 ----------------------------------------------

    def _load_rag(self, raw: dict) -> RagConfig:
        rag = raw.get("rag")
        if not isinstance(rag, dict):
            raise TypeError(f"运行时配置缺少 rag 段 | dir={self._config_dir}")

        try:
            return RagConfig(
                execution_timeout_seconds=self._positive_number(
                    rag["execution_timeout_seconds"],
                    "rag.execution_timeout_seconds",
                ),
                rag_max_concurrency=self._integer(
                    rag["max_concurrency"],
                    "rag.max_concurrency",
                ),
                retry_ms=self._integer(
                    rag["retry_ms"],
                    "rag.retry_ms",
                    minimum=0,
                ),
                locales=self._load_rag_locales(rag.get("locales")),
            )
        except KeyError as e:
            raise ValueError(f"rag 缺少必填字段: {e}") from e

    @staticmethod
    def _positive_number(value: object, path: str) -> float:
        """超时必须是有限正数，不做字符串或布尔值转换。"""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path} 必须是有限正数")
        timeout = float(value)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError(f"{path} 必须是有限正数")
        return timeout

    @staticmethod
    def _integer(value: object, path: str, *, minimum: int = 1) -> int:
        if type(value) is not int or value < minimum:
            raise ValueError(f"{path} 必须是大于等于 {minimum} 的整数")
        return value

    @staticmethod
    def _text(value: object, path: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path} 必须是非空字符串")
        return value

    def _load_rag_locales(self, locales_raw: Any) -> dict[str, LocaleConfig]:
        if not isinstance(locales_raw, dict) or not locales_raw:
            raise ValueError(f"运行时配置缺少 rag.locales 段 | dir={self._config_dir}")

        locales: dict[str, LocaleConfig] = {}
        for locale, section in locales_raw.items():
            if not isinstance(section, dict):
                raise TypeError(
                    f"locale '{locale}' 配置格式错误 | dir={self._config_dir}"
                )
            try:
                locales[locale] = LocaleConfig(
                    guardrail_prompt_template=self._text(
                        section["guardrail_prompt_template"],
                        f"rag.locales.{locale}.guardrail_prompt_template",
                    ),
                    ref_label=self._text(
                        section["ref_label"], f"rag.locales.{locale}.ref_label"
                    ),
                    query_label=self._text(
                        section["query_label"], f"rag.locales.{locale}.query_label"
                    ),
                    system_prompt=self._text(
                        section["system_prompt"], f"rag.locales.{locale}.system_prompt"
                    ),
                )
            except KeyError as e:
                raise ValueError(f"locale '{locale}' 缺少必填字段: {e}") from e
        default_locale = I18nConfigLoader().load().default_locale
        if default_locale not in locales:
            raise ValueError(f"rag.locales 缺少系统默认语言：{default_locale}")
        return locales

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)
