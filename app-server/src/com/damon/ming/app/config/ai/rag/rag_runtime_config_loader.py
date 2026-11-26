# app-server/src/com/damon/ming/app/config/ai/rag/rag_runtime_config_loader.py
# RAG 运行时配置加载器 —— 流程配置和多语言文本。

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.app.config.env import get_model_root_dir
from src.com.damon.ming.app.config.i18n.i18n_config_loader import I18nConfigLoader
from src.com.damon.ming.utils.yaml_loader import load_yaml

# ═══════════════════════════════════════════════════════════════════════
# 数据类 —— 与 rag-runtime.yaml 的段落一一对应
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LocaleConfig:
    """rag.locales.{locale} 段 —— 单个 locale 的聊天文本。"""

    ref_label: str
    query_label: str
    system_prompt: str


@dataclass(frozen=True)
class RagConfig:
    """rag 段。"""

    execution_timeout_seconds: float  # 检索、上下文构造和主推理预算（秒），不含护栏
    rag_max_concurrency: int
    retry_ms: int
    model_root_dir: str
    locales: dict[str, LocaleConfig]


@dataclass(frozen=True)
class RagRuntimeConfig:
    """rag-runtime.yaml 的直接映射。

    rag —— 流程并发、超时和 locales 文本。
    constructor —— 章节重建的来源与标题标签格式。
    embedding —— 网关超时及各 role 的模型和文本规则。
    rerank —— 各重排 role 的模型及窗口、分数策略。
    retriever —— 各检索 role 的候选池、融合和超时参数。
    splitter —— 文档切分的重叠与 section 大小策略。
    summary —— 摘要提示词和分段比例。
    source —— 数据源处理、预分块及 OCR 参数。
    tokenizer —— LLM 计数和 BM25 分词器实例。
    thread_pools —— RAG 资源组内部的 worker 分配。
    """

    rag: RagConfig
    constructor: dict[str, Any]
    embedding: dict[str, Any]
    rerank: dict[str, Any]
    retriever: dict[str, Any]
    splitter: dict[str, Any]
    summary: dict[str, Any]
    source: dict[str, Any]
    tokenizer: dict[str, Any]
    thread_pools: dict[str, Any]


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
            constructor=self._load_constructor(raw),
            embedding=self._load_embedding(raw),
            rerank=self._load_rerank(raw),
            retriever=self._load_retriever(raw),
            splitter=self._load_splitter(raw),
            summary=self._load_summary(raw),
            source=self._load_source(raw),
            tokenizer=self._load_tokenizer(raw),
            thread_pools=self._load_thread_pools(raw),
        )
        return self._config

    @staticmethod
    def _load_thread_pools(raw: dict) -> dict[str, Any]:
        section = raw.get("thread_pools")
        if not isinstance(section, dict) or not section:
            raise TypeError("RAG thread_pools 配置必须是非空键值对象")
        return section

    @staticmethod
    def _load_source(raw: dict) -> dict[str, Any]:
        section = raw.get("source")
        if not isinstance(section, dict):
            raise TypeError("RAG source 配置必须是键值对象")
        return section

    @staticmethod
    def _load_tokenizer(raw: dict) -> dict[str, Any]:
        tokenizer = raw.get("tokenizer")
        if not isinstance(tokenizer, dict):
            raise TypeError("RAG tokenizer 配置必须是键值对象")
        return tokenizer

    @staticmethod
    def _load_summary(raw: dict) -> dict[str, Any]:
        summary = raw.get("summary")
        if not isinstance(summary, dict):
            raise TypeError("RAG summary 配置必须是键值对象")
        return summary

    @staticmethod
    def _load_splitter(raw: dict) -> dict[str, Any]:
        splitter = raw.get("splitter")
        if not isinstance(splitter, dict):
            raise TypeError("RAG splitter 配置必须是键值对象")
        return splitter

    @staticmethod
    def _load_retriever(raw: dict) -> dict[str, Any]:
        retriever = raw.get("retriever")
        if not isinstance(retriever, dict):
            raise TypeError("RAG retriever 配置必须是键值对象")
        return retriever

    @staticmethod
    def _load_rerank(raw: dict) -> dict[str, Any]:
        rerank = raw.get("rerank")
        if not isinstance(rerank, dict):
            raise TypeError("RAG rerank 配置必须是键值对象")
        return rerank

    @staticmethod
    def _load_embedding(raw: dict) -> dict[str, Any]:
        embedding = raw.get("embedding")
        if not isinstance(embedding, dict):
            raise TypeError("RAG embedding 配置必须是 YAML 对象")
        return embedding

    @staticmethod
    def _load_constructor(raw: dict) -> dict[str, Any]:
        constructor = raw.get("constructor")
        if not isinstance(constructor, dict):
            raise TypeError("运行时配置缺少 constructor 段")
        return constructor

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
                model_root_dir=get_model_root_dir(),
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
