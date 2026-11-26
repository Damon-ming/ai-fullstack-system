# app-server/src/com/damon/ming/app/config/ai/rag/rag_runtime_config_loader.py
# RAG 运行时配置加载器 —— 流程配置和多语言文本。

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.com.damon.ming.ai.rag.embedding.params import VLLMEmbeddingParams
from src.com.damon.ming.ai.rag.rerank.base_reranker import RerankerParams
from src.com.damon.ming.app.config.ai.rag.source_config import SourceConfig
from src.com.damon.ming.app.config.ai.rag.source_config_parser import SourceConfigParser
from src.com.damon.ming.app.config.ai_runtime_config import (
    get_model_dimension,
    get_model_max_input_tokens,
    get_model_max_len,
)
from src.com.damon.ming.app.config.env import (
    get_inference_gateway_url,
    get_model_root_dir,
)
from src.com.damon.ming.app.config.i18n.i18n_config_loader import I18nConfigLoader
from src.com.damon.ming.utils.yaml_loader import load_yaml

# ═══════════════════════════════════════════════════════════════════════
# 数据类 —— 与 rag-runtime.yaml 的段落一一对应
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConstructorConfig:
    """章节重建的来源与标题标签格式。"""

    source_label_template: str
    heading_label_template: str
    heading_separator: str


@dataclass(frozen=True)
class RetrieverConfig:
    """检索器构造、候选池及最终输出参数。"""

    name: str
    top_k: int
    retrieve_top_k: int
    dense_top_k: int
    sparse_top_k: int
    dedup_by_section: bool
    dense_weight: float
    sparse_weight: float
    fuse_k: int
    retrieval_timeout_seconds: float
    max_section_oversample_multiplier: int = 5
    rrf_oversample_multiplier: int = 3


@dataclass(frozen=True)
class RetrieverRuntimeConfig:
    roles: dict[str, RetrieverConfig]


@dataclass(frozen=True)
class SplitterRuntimeConfig:
    chunk_overlap: int
    max_grouped_chunks_per_section: int
    max_headed_chunks_per_section: int

    def __post_init__(self) -> None:
        if type(self.chunk_overlap) is not int or self.chunk_overlap < 0:
            raise ValueError("chunk_overlap 必须是非负整数")
        if (
            type(self.max_grouped_chunks_per_section) is not int
            or self.max_grouped_chunks_per_section <= 0
        ):
            raise ValueError("max_grouped_chunks_per_section 必须是正整数")
        if (
            type(self.max_headed_chunks_per_section) is not int
            or self.max_headed_chunks_per_section <= 0
        ):
            raise ValueError("max_headed_chunks_per_section 必须是正整数")


@dataclass(frozen=True)
class SummaryRuntimeConfig:
    system_prompt_template: str
    context_message_template: str
    context_margin_ratio: float | None
    context_overlap_ratio: float | None


@dataclass(frozen=True)
class TokenizerRoleConfig:
    tokenizer_engine: str
    params: dict[str, Any]


@dataclass(frozen=True)
class TokenizerRuntimeConfig:
    roles: dict[str, TokenizerRoleConfig]


@dataclass(frozen=True)
class RagThreadPoolConfig:
    """RAG 资源组内部各命名线程池的 worker 数。"""

    workers: dict[str, int]


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
class EmbeddingRoleConfig:
    """Embedding role 的模型、凭据、文本规则和批量大小。"""

    model_name: str
    api_key: str
    query_prefix: str
    passage_prefix: str
    batch_size: int


@dataclass(frozen=True)
class EmbeddingRuntimeConfig:
    timeout_seconds: float
    roles: dict[str, EmbeddingRoleConfig]


@dataclass(frozen=True)
class RerankRuntimeConfig:
    roles: dict[str, RerankerParams]


def build_embedding_params(
    model_root_dir: Path, config: EmbeddingRuntimeConfig
) -> dict[str, VLLMEmbeddingParams]:
    """结合网关地址和模型规格构造各 role 的 vLLM embedding 参数。"""
    if not config.roles:
        raise ValueError("Embedding Gateway 配置缺少 roles")

    base_url = get_inference_gateway_url()
    cache_folder = str(model_root_dir / "embedding")
    loaded: dict[str, VLLMEmbeddingParams] = {}
    for role, entry in config.roles.items():
        model_name = entry.model_name
        max_tokens = get_model_max_input_tokens(model_name)
        dimension = get_model_dimension(model_name)
        max_model_len = get_model_max_len(model_name)
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError(
                f"Embedding role '{role}' 的 max_input_tokens 必须是正整数"
            )
        if type(dimension) is not int or dimension <= 0:
            raise ValueError(f"Embedding role '{role}' 的 dimension 必须是正整数")
        if max_tokens > max_model_len:
            raise ValueError(
                f"Embedding role '{role}' 的 max_input_tokens 不能大于模型 max-model-len"
            )
        loaded[role] = VLLMEmbeddingParams(
            model_name=model_name,
            base_url=base_url,
            api_key=entry.api_key,
            timeout=config.timeout_seconds,
            max_input_tokens=max_tokens,
            dimension=dimension,
            cache_folder=cache_folder,
            batch_size=entry.batch_size,
            query_prefix=entry.query_prefix,
            passage_prefix=entry.passage_prefix,
        )
    return loaded


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
    constructor: ConstructorConfig
    embedding: EmbeddingRuntimeConfig
    rerank: RerankRuntimeConfig
    retriever: RetrieverRuntimeConfig
    splitter: SplitterRuntimeConfig
    summary: SummaryRuntimeConfig
    source: SourceConfig
    tokenizer: TokenizerRuntimeConfig
    thread_pools: RagThreadPoolConfig


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
            source=SourceConfigParser.parse(raw.get("source")),
            tokenizer=self._load_tokenizer(raw),
            thread_pools=self._load_thread_pools(raw),
        )
        return self._config

    @staticmethod
    def _load_thread_pools(raw: dict) -> RagThreadPoolConfig:
        section = raw.get("thread_pools")
        if not isinstance(section, dict) or not section:
            raise TypeError("RAG thread_pools 配置必须是非空键值对象")
        workers: dict[str, int] = {}
        for name, count in section.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("RAG 线程池名称必须是非空字符串")
            if type(count) is not int or count <= 0:
                raise ValueError(f"RAG 线程池 {name} 的 worker 数必须是正整数")
            workers[name] = count
        missing = {"retrieval", "document", "rerank", "bm25"} - workers.keys()
        if missing:
            raise ValueError(
                f"RAG thread_pools 缺少线程池: {', '.join(sorted(missing))}"
            )
        return RagThreadPoolConfig(workers=workers)

    @staticmethod
    def _load_tokenizer(raw: dict) -> TokenizerRuntimeConfig:
        tokenizer = raw.get("tokenizer")
        if not isinstance(tokenizer, dict):
            raise TypeError("RAG tokenizer 配置必须是键值对象")
        raw_roles = tokenizer.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("RAG tokenizer 配置缺少 roles")

        roles: dict[str, TokenizerRoleConfig] = {}
        for name, entry in raw_roles.items():
            if not isinstance(entry, dict):
                raise TypeError(f"分词器配置 '{name}' 必须是键值对象")
            engine = entry.get("tokenizer_engine")
            if not engine:
                raise ValueError("配置缺少 tokenizer_engine 字段")
            params = entry.get("params", {})
            if not isinstance(params, dict):
                raise TypeError(f"分词器 '{name}' 的 params 必须是键值对象")
            if engine == "tiktoken":
                encoding_name = params.get("encoding_name")
                if not isinstance(encoding_name, str) or not encoding_name.strip():
                    raise ValueError(f"分词器 '{name}' 缺少有效的 params.encoding_name")
            elif engine == "jieba":
                dicts_dir = params.get("dicts_dir")
                if dicts_dir is not None and not isinstance(dicts_dir, str):
                    raise TypeError(f"分词器 '{name}' 的 params.dicts_dir 必须是字符串")
            else:
                raise ValueError(f"分词器引擎 '{engine}' 尚未配置对应的参数解析器")
            roles[name] = TokenizerRoleConfig(tokenizer_engine=engine, params=params)
        return TokenizerRuntimeConfig(roles=roles)

    @staticmethod
    def _load_summary(raw: dict) -> SummaryRuntimeConfig:
        summary = raw.get("summary")
        if not isinstance(summary, dict):
            raise TypeError("RAG summary 配置必须是键值对象")

        context_margin_ratio = summary.get("context_margin_ratio")
        if context_margin_ratio is not None:
            if isinstance(context_margin_ratio, bool) or not isinstance(
                context_margin_ratio, (int, float)
            ):
                raise TypeError("summary.context_margin_ratio 必须是数值或 null")
            if not 0 <= context_margin_ratio < 1:
                raise ValueError("summary.context_margin_ratio 必须大于等于 0 且小于 1")

        context_overlap_ratio = summary.get("context_overlap_ratio")
        if context_overlap_ratio is not None:
            if isinstance(context_overlap_ratio, bool) or not isinstance(
                context_overlap_ratio, (int, float)
            ):
                raise TypeError("summary.context_overlap_ratio 必须是数值或 null")
            if not 0 <= context_overlap_ratio < 0.5:
                raise ValueError(
                    "summary.context_overlap_ratio 必须大于等于 0 且小于 0.5"
                )

        context_message_template = summary.get("context_message_template")
        if (
            not isinstance(context_message_template, str)
            or not context_message_template.strip()
        ):
            raise ValueError("summary.context_message_template 必须是非空字符串")
        if any(
            placeholder not in context_message_template
            for placeholder in ("{context}", "{content}")
        ):
            raise ValueError(
                "summary.context_message_template 必须包含 {context} 和 {content}"
            )

        system_prompt_template = summary.get("system_prompt_template")
        if (
            not isinstance(system_prompt_template, str)
            or not system_prompt_template.strip()
        ):
            raise ValueError("summary.system_prompt_template 必须是非空字符串")
        if "{max_tokens}" not in system_prompt_template:
            raise ValueError("summary.system_prompt_template 必须包含 {max_tokens}")

        return SummaryRuntimeConfig(
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

    @staticmethod
    def _load_splitter(raw: dict) -> SplitterRuntimeConfig:
        splitter = raw.get("splitter")
        if not isinstance(splitter, dict):
            raise TypeError("RAG splitter 配置必须是键值对象")
        try:
            return SplitterRuntimeConfig(
                chunk_overlap=(
                    0
                    if splitter.get("chunk_overlap") is None
                    else splitter["chunk_overlap"]
                ),
                max_grouped_chunks_per_section=splitter[
                    "max_grouped_chunks_per_section"
                ],
                max_headed_chunks_per_section=splitter["max_headed_chunks_per_section"],
            )
        except KeyError as exc:
            raise ValueError(f"分割器配置缺少必填字段: {exc}") from exc

    @staticmethod
    def _load_retriever(raw: dict) -> RetrieverRuntimeConfig:
        retriever = raw.get("retriever")
        if not isinstance(retriever, dict):
            raise TypeError("RAG retriever 配置必须是键值对象")
        raw_roles = retriever.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("RAG retriever 配置缺少 roles")

        roles: dict[str, RetrieverConfig] = {}
        for name, section in raw_roles.items():
            if not isinstance(section, dict):
                raise TypeError(f"检索器配置 '{name}' 必须是键值对象")
            params = section.get("params", {})
            if not isinstance(params, dict):
                raise TypeError(f"检索器配置 '{name}' 的 params 必须是键值对象")
            timeout = section.get("retrieval_timeout_seconds")
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout)
                or timeout <= 0
            ):
                raise ValueError(
                    f"检索器配置 '{name}' 的 retrieval_timeout_seconds 必须是有限正数"
                )
            try:
                roles[name] = RetrieverConfig(
                    name=name,
                    top_k=section["top_k"],
                    retrieve_top_k=section["retrieve_top_k"],
                    dense_top_k=section["dense_top_k"],
                    sparse_top_k=section["sparse_top_k"],
                    dedup_by_section=section["dedup_by_section"],
                    dense_weight=section["dense_weight"],
                    sparse_weight=section["sparse_weight"],
                    fuse_k=section["fuse_k"],
                    retrieval_timeout_seconds=timeout,
                    max_section_oversample_multiplier=params.get(
                        "max_section_oversample_multiplier", 5
                    ),
                    rrf_oversample_multiplier=params.get(
                        "rrf_oversample_multiplier", 3
                    ),
                )
            except KeyError as exc:
                raise ValueError(f"检索器配置 '{name}' 缺少必填字段: {exc}") from exc
        return RetrieverRuntimeConfig(roles=roles)

    @staticmethod
    def _load_rerank(raw: dict) -> RerankRuntimeConfig:
        rerank = raw.get("rerank")
        if not isinstance(rerank, dict):
            raise TypeError("RAG rerank 配置必须是键值对象")
        raw_roles = rerank.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("RAG rerank 配置缺少 roles")

        known_fields = {f.name for f in RerankerParams.__dataclass_fields__.values()}
        roles: dict[str, RerankerParams] = {}
        for name, config in raw_roles.items():
            if not isinstance(config, dict):
                raise TypeError(f"重排器配置 '{name}' 必须是键值对象")
            base_kwargs = {
                key: value for key, value in config.items() if key in known_fields
            }
            extra_kwargs = {
                key: value for key, value in config.items() if key not in known_fields
            }
            try:
                roles[name] = RerankerParams(**base_kwargs, extra=extra_kwargs)
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"重排器配置 '{name}' 无效: {exc}") from exc
        return RerankRuntimeConfig(roles=roles)

    @staticmethod
    def _load_embedding(raw: dict) -> EmbeddingRuntimeConfig:
        embedding = raw.get("embedding")
        if not isinstance(embedding, dict):
            raise TypeError("RAG embedding 配置必须是 YAML 对象")
        transport = embedding.get("transport")
        if not isinstance(transport, dict):
            raise TypeError("Embedding Gateway 配置缺少 transport")
        timeout = transport.get("timeout_seconds")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("Embedding transport.timeout_seconds 必须是有限正数")
        raw_roles = embedding.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("RAG embedding 配置缺少 roles")

        roles: dict[str, EmbeddingRoleConfig] = {}
        for role, entry in raw_roles.items():
            if not isinstance(entry, dict):
                raise TypeError(f"Embedding role '{role}' 配置必须是 YAML 对象")
            model_name = entry.get("model_name")
            api_key = entry.get("api_key")
            if not isinstance(model_name, str) or not model_name.strip():
                raise ValueError(f"Embedding role '{role}' 缺少有效的 model_name")
            if not isinstance(api_key, str) or not api_key.strip():
                raise ValueError(f"Embedding role '{role}' 的 api_key 必须是非空字符串")
            batch_size = entry.get("batch_size")
            query_prefix = entry.get("query_prefix", "")
            passage_prefix = entry.get("passage_prefix", "")
            if type(batch_size) is not int or batch_size < 1:
                raise ValueError(f"Embedding role '{role}' 的 batch_size 必须是正整数")
            if not isinstance(query_prefix, str) or not isinstance(passage_prefix, str):
                raise TypeError(f"Embedding role '{role}' 的文本前缀必须是字符串")
            roles[role] = EmbeddingRoleConfig(
                model_name=model_name,
                api_key=api_key,
                query_prefix=query_prefix,
                passage_prefix=passage_prefix,
                batch_size=batch_size,
            )
        return EmbeddingRuntimeConfig(timeout_seconds=float(timeout), roles=roles)

    @staticmethod
    def _load_constructor(raw: dict) -> ConstructorConfig:
        constructor = raw.get("constructor")
        if not isinstance(constructor, dict):
            raise TypeError("运行时配置缺少 constructor 段")

        templates = {}
        for key in ("source_label_template", "heading_label_template"):
            value = constructor.get(key)
            if not isinstance(value, str) or "{value}" not in value:
                raise ValueError(f"constructor.{key} 必须是包含 {{value}} 的字符串")
            templates[key] = value

        heading_separator = constructor.get("heading_separator")
        if not isinstance(heading_separator, str) or not heading_separator:
            raise ValueError("constructor.heading_separator 必须是非空字符串")

        return ConstructorConfig(
            source_label_template=templates["source_label_template"],
            heading_label_template=templates["heading_label_template"],
            heading_separator=heading_separator,
        )

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
