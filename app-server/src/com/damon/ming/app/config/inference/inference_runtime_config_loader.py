# app-server/src/com/damon/ming/app/config/inference/inference_runtime_config_loader.py
# 推理运行时配置加载器 —— YAML 直接映射 + 推理引擎装配。
#
# 连接路径：
#   app-server → inference-gateway (http://inference-gateway:8080/v1)
#                              → 按 api_key 路由到 vllm-{role}
#
# api_key 由环境变量注入（由 docker-compose 提供），格式：
#   INFERENCE_API_KEYS        → JSON 字典，如 {"chat":"ak_pool_001","intent":"ak_pool_002"}
#   INFERENCE_API_KEY_{ROLE}  → 单个角色，优先级高于 JSON
#
# 由 AppInitializer 持有唯一实例并注入下游（rag_tool 通过参数接收，
# 引擎实例各自持有连接池，必须只装配一次）：
#   loader = InferenceConfigLoader()
#   cfg = loader.load()
#
#   cfg.chat.common.infer_sem                # chat.common 段
#   cfg.chat.locales["zh_CN"].system_prompt  # chat.locales 段
#   cfg.roles["chat"].options["max_tokens"]  # roles 段原始参数
#   cfg.roles["chat"].engine                 # 该角色绑定的引擎实例

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
    get_inference_timeout,
)

# ── 连接参数来源：环境变量（由 docker-compose 注入）────────────────────
# INFERENCE_GATEWAY_URL: 推理网关地址，如 http://inference-gateway:8080/v1
# INFERENCE_SERVER:      引擎类型，如 ollama / vllm / sglang
# INFERENCE_TIMEOUT:     超时秒数（可选，默认 180）
# INFERENCE_API_KEYS:    JSON 字典 {role: api_key}（必须覆盖所有角色，否则启动报错）
# INFERENCE_API_KEY_{ROLE}: 单个角色的 api_key（优先级高于 JSON）

# api_key 完全由环境变量注入，不设默认值。
# 未配置的角色在 load() 中明确报错。


# ═══════════════════════════════════════════════════════════════════════
# 数据类 —— 与 inference-runtime.yaml 的段落一一对应
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ChatCommonConfig:
    """chat.common 段 —— 聊天流程并发控制参数。"""

    total_timeout: int  # RAG + 推理总预算（秒）
    infer_sem: int  # 推理信号量上限（主推理 + 摘要/压缩共享）
    rag_sem: int  # RAG 检索段信号量上限（反压控制）
    guardrail_sem: int  # 护栏 LLM 调用信号量上限
    guardrail_timeout: int  # 护栏检测独立超时（秒），超时 fail-open 放行
    sse_retry_ms: int  # SSE 断连重连间隔（毫秒），0=禁用


@dataclass(frozen=True)
class LocaleConfig:
    """chat.locales.{locale} 段 —— 单个 locale 的聊天文本。"""

    ref_label: str
    query_label: str
    system_prompt: str


@dataclass(frozen=True)
class ChatConfig:
    """chat 段。"""

    common: ChatCommonConfig
    locales: dict[str, LocaleConfig]


@dataclass(frozen=True)
class ModelEntry:
    """roles.{role} 段 + 该角色绑定的引擎实例。

    options 是 YAML 中该角色的原始推理参数（temperature/top_p/max_tokens）；
    引擎实例由加载器按环境变量连接参数装配，api_key 相同的角色共享同一实例。
    """

    model_name: str
    options: dict[str, Any]
    api_key: str
    engine_type: str
    engine: BaseInferenceService


@dataclass(frozen=True)
class InferenceRuntimeConfig:
    """inference-runtime.yaml 的直接映射。

    chat  —— chat 段（common 并发参数 + locales 文本）
    roles —— roles 段，每个角色携带 YAML 参数和装配出的引擎实例
    """

    chat: ChatConfig
    roles: dict[str, ModelEntry]


# ═══════════════════════════════════════════════════════════════════════
# 加载器
# ═══════════════════════════════════════════════════════════════════════


class InferenceConfigLoader:
    """推理运行时配置加载器。

    由 AppInitializer 持有唯一实例，需要推理配置的模块通过参数接收，
    不要自行构造 —— 引擎实例各自持有连接池，多造一个加载器就多一套引擎。

        loader = InferenceConfigLoader()
        cfg = loader.load()

    load() 只执行一次，重复调用直接返回缓存结果。
    """

    def __init__(self) -> None:
        self._config_dir: str = os.path.dirname(os.path.abspath(__file__))
        self._config: InferenceRuntimeConfig | None = None

    def load(self) -> InferenceRuntimeConfig:
        """加载 inference-runtime.yaml 并装配推理引擎。

        chat / roles 参数是 YAML 的直接映射；roles 的引擎实例由环境变量
        连接参数装配。结果缓存，重复调用直接返回。
        """
        if self._config is not None:
            return self._config

        raw = self._read_yaml()
        self._config = InferenceRuntimeConfig(
            chat=self._load_chat(raw),
            roles=self._assemble_roles(self._read_roles(raw)),
        )
        return self._config

    # ---- 私有：引擎装配 -------------------------------------------------

    def _assemble_roles(
        self, roles_raw: dict[str, dict[str, Any]]
    ) -> dict[str, ModelEntry]:
        engine_type = get_inference_server()
        base_url = get_inference_gateway_url()
        timeout = get_inference_timeout()
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
            engine_key = api_key or "__shared__"
            if engine_key not in engines:
                engines[engine_key] = impl_cls(
                    InferenceParams(
                        base_url=base_url,
                        timeout=timeout,
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

    def _load_chat(self, raw: dict) -> ChatConfig:
        chat = raw.get("chat")
        if not isinstance(chat, dict):
            raise TypeError(f"运行时配置缺少 chat 段 | dir={self._config_dir}")

        return ChatConfig(
            common=self._load_chat_common(chat.get("common")),
            locales=self._load_chat_locales(chat.get("locales")),
        )

    def _load_chat_common(self, common_raw: Any) -> ChatCommonConfig:
        if not isinstance(common_raw, dict):
            raise TypeError(f"运行时配置缺少 chat.common 段 | dir={self._config_dir}")
        try:
            pipeline = common_raw["pipeline"]
            inference = pipeline["inference"]
            rag = pipeline["rag"]
            guardrail = common_raw["guardrail"]
            return ChatCommonConfig(
                total_timeout=int(pipeline["total_timeout"]),
                infer_sem=int(inference["semaphore"]),
                rag_sem=int(rag["semaphore"]),
                guardrail_sem=int(guardrail["semaphore"]),
                guardrail_timeout=int(guardrail["timeout"]),
                sse_retry_ms=int(common_raw["sse_retry_ms"]),
            )
        except (KeyError, TypeError) as e:
            raise ValueError(f"chat.common 缺少必填字段: {e}") from e

    def _load_chat_locales(self, locales_raw: Any) -> dict[str, LocaleConfig]:
        if not isinstance(locales_raw, dict) or not locales_raw:
            raise ValueError(f"运行时配置缺少 chat.locales 段 | dir={self._config_dir}")

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
            raise ValueError(f"运行时配置缺少 roles 段 | dir={self._config_dir}")

        cleaned: dict[str, dict[str, Any]] = {}
        for role, params in roles.items():
            if not isinstance(params, dict):
                raise TypeError(f"角色 '{role}' 配置格式错误 | dir={self._config_dir}")
            cleaned[role] = dict(params)
        return cleaned

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)
