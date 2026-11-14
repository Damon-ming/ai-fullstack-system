# app-server/src/com/damon/ming/app/config/rag/rag_runtime_config_loader.py
# RAG 运行时配置加载器 —— YAML 直接映射 + 推理引擎装配。
#
# 连接路径：
#   app-server → inference-gateway (http://inference-gateway:8080/v1)
#                              → 按 api_key 路由到 vllm-{role}
#
# api_key 由环境变量注入（由 docker-compose 提供），格式：
#   INFERENCE_API_KEYS        → JSON 字典，如 {"inference":"ak_pool_001","intent":"ak_pool_002"}
#   INFERENCE_API_KEY_{ROLE}  → 单个角色，优先级高于 JSON
#
# 由 AppInitializer 持有唯一实例并注入下游（rag_tool 通过参数接收，
# 引擎实例各自持有连接池，必须只装配一次）：
#   loader = RagConfigLoader()
#   cfg = loader.load()
#
#   cfg.rag.shared_inference_max_concurrency  # 主推理与摘要共享的并发限制
#   cfg.rag.locales["zh_CN"].system_prompt  # YAML rag.locales 段
#   cfg.rag.roles["inference"].options["max_tokens"]  # 角色参数
#   cfg.rag.roles["inference"].engine                 # 角色引擎

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.ai.inference import resolve_engine
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
)
from src.com.damon.ming.app.config._yaml import load_yaml
from src.com.damon.ming.app.config.env import (
    get_inference_api_keys,
    get_inference_gateway_url,
    get_inference_server,
)
from src.com.damon.ming.app.config.thread import ThreadPoolConfigLoader

# ── 连接参数来源：环境变量（由 docker-compose 注入）────────────────────
# INFERENCE_GATEWAY_URL: 推理网关地址，如 http://inference-gateway:8080/v1
# INFERENCE_SERVER:      引擎类型，如 ollama / vllm / sglang
# INFERENCE_API_KEYS:    JSON 字典 {role: api_key}（必须覆盖所有角色，否则启动报错）
# INFERENCE_API_KEY_{ROLE}: 单个角色的 api_key（优先级高于 JSON）

# api_key 完全由环境变量注入，不设默认值。
# 未配置的角色在 load() 中明确报错。


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

    execution_timeout_seconds: int  # 检索、上下文构造和主推理预算（秒），不含护栏
    thread_pools: dict[str, int]
    shared_inference_max_concurrency: int
    retrieval_max_concurrency: int
    guardrail_max_concurrency: int
    guardrail_timeout_seconds: int
    inference_timeout_seconds: float  # 推理客户端网络超时，与执行预算独立
    sse_retry_ms: int
    roles: dict[str, ModelEntry]
    locales: dict[str, LocaleConfig]


@dataclass(frozen=True)
class ModelEntry:
    """rag.roles.{role} 段 + 该角色绑定的引擎实例。

    options 是 YAML 中该角色的原始推理参数（temperature/top_p/max_tokens）；
    引擎实例由加载器按环境变量连接参数装配，api_key 相同的角色共享同一实例。
    """

    model_name: str
    options: dict[str, Any]
    api_key: str
    engine_type: str
    engine: BaseInferenceService


@dataclass(frozen=True)
class RagRuntimeConfig:
    """rag-runtime.yaml 的直接映射。

    rag —— rag 段（并发参数、角色引擎和 locales 文本）。
    """

    rag: RagConfig


# ═══════════════════════════════════════════════════════════════════════
# 加载器
# ═══════════════════════════════════════════════════════════════════════


class RagConfigLoader:
    """RAG 运行时配置加载器。

    由 AppInitializer 持有唯一实例，需要推理配置的模块通过参数接收，
    不要自行构造 —— 引擎实例各自持有连接池，多造一个加载器就多一套引擎。

        loader = RagConfigLoader()
        cfg = loader.load()

    load() 只执行一次，重复调用直接返回缓存结果。
    """

    def __init__(self) -> None:
        self._config_dir: str = os.path.dirname(os.path.abspath(__file__))
        self._config: RagRuntimeConfig | None = None

    def load(self) -> RagRuntimeConfig:
        """加载 rag-runtime.yaml 并装配推理引擎。

        rag 参数是 YAML 的直接映射；rag.roles 的引擎实例由环境变量
        连接参数装配。结果缓存，重复调用直接返回。
        """
        if self._config is not None:
            return self._config

        raw = self._read_yaml()
        self._config = RagRuntimeConfig(
            rag=self._load_rag(raw),
        )
        return self._config

    # ---- 私有：引擎装配 -------------------------------------------------

    def _assemble_roles(
        self, roles_raw: dict[str, dict[str, Any]], *, timeout_seconds: float
    ) -> dict[str, ModelEntry]:
        engine_type = get_inference_server()
        base_url = get_inference_gateway_url()
        api_keys = get_inference_api_keys()

        # 所有角色必须有 api_key 配置
        missing_roles = [r for r in roles_raw if r not in api_keys]
        if missing_roles:
            raise RuntimeError(
                f"以下推理角色缺少 api_key 配置（环境变量 INFERENCE_API_KEY_{{ROLE}} "
                f"或 INFERENCE_API_KEYS JSON）：{', '.join(missing_roles)}"
            )

        impl_cls = resolve_engine(engine_type)
        engines: dict[str, BaseInferenceService] = {}
        entries: dict[str, ModelEntry] = {}

        for role, options in roles_raw.items():
            api_key = api_keys[role]

            # api_key 相同的角色共享引擎（如 guardrail 复用 intent）
            engine_key = api_key
            if engine_key not in engines:
                engines[engine_key] = impl_cls(
                    InferenceParams(
                        base_url=base_url,
                        timeout=timeout_seconds,
                        api_key=api_key,
                    )
                )

            # 网关模式下 model 由 gateway 注入，这里用 role 占位
            entries[role] = ModelEntry(
                model_name=role,
                options=options,
                api_key=api_key,
                engine_type=engine_type,
                engine=engines[engine_key],
            )

        return entries

    # ---- 私有：YAML 段映射 ----------------------------------------------

    def _load_rag(self, raw: dict) -> RagConfig:
        rag = raw.get("rag")
        if not isinstance(rag, dict):
            raise TypeError(f"运行时配置缺少 rag 段 | dir={self._config_dir}")

        try:
            pipeline = rag["pipeline"]
            shared_inference = pipeline["shared_inference"]
            retrieval = pipeline["retrieval"]
            guardrail = pipeline["guardrail"]
            timeout_seconds = self._parse_inference_timeout(
                rag["transport"]["inference"]["timeout_seconds"]
            )
            return RagConfig(
                thread_pools=self._load_thread_pools(pipeline.get("thread_pools")),
                execution_timeout_seconds=int(pipeline["execution_timeout_seconds"]),
                shared_inference_max_concurrency=int(
                    shared_inference["max_concurrency"]
                ),
                retrieval_max_concurrency=int(retrieval["max_concurrency"]),
                guardrail_max_concurrency=int(guardrail["max_concurrency"]),
                guardrail_timeout_seconds=int(guardrail["timeout_seconds"]),
                inference_timeout_seconds=timeout_seconds,
                sse_retry_ms=int(rag["transport"]["sse"]["retry_ms"]),
                roles=self._assemble_roles(
                    self._read_roles(rag), timeout_seconds=timeout_seconds
                ),
                locales=self._load_rag_locales(rag.get("locales")),
            )
        except (KeyError, TypeError) as e:
            raise ValueError(f"rag 缺少必填字段: {e}") from e

    @staticmethod
    def _parse_inference_timeout(value: object) -> float:
        """网络超时必须是有限正数，不提供缺省值。"""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("rag.transport.inference.timeout_seconds 必须是正数")
        timeout = float(value)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("rag.transport.inference.timeout_seconds 必须是有限正数")
        return timeout

    def _load_thread_pools(self, raw: object) -> dict[str, int]:
        pools = ThreadPoolConfigLoader.parse_pools(raw)
        required = {"retrieval", "document", "rerank", "bm25"}
        missing = required - pools.keys()
        if missing:
            raise ValueError(
                f"rag.pipeline.thread_pools 缺少必需线程池：{', '.join(sorted(missing))}"
            )
        return pools

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
                    ref_label=str(section["ref_label"]),
                    query_label=str(section["query_label"]),
                    system_prompt=str(section["system_prompt"]),
                )
            except KeyError as e:
                raise ValueError(f"locale '{locale}' 缺少必填字段: {e}") from e
        return locales

    def _read_roles(self, raw: dict) -> dict[str, dict[str, Any]]:
        roles = raw.get("roles")
        if not isinstance(roles, dict) or not roles:
            raise ValueError(f"运行时配置缺少 rag.roles 段 | dir={self._config_dir}")

        cleaned: dict[str, dict[str, Any]] = {}
        for role, params in roles.items():
            if not isinstance(params, dict):
                raise TypeError(f"角色 '{role}' 配置格式错误 | dir={self._config_dir}")
            cleaned[role] = dict(params)
        return cleaned

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)
