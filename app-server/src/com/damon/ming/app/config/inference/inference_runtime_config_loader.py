# app-server/src/com/damon/ming/app/config/inference/inference_runtime_config_loader.py
# 推理运行时配置加载器 —— 运行时配置 + 网关路由 + 聊天并发控制。
#
# 连接路径：
#   app-server → inference-gateway (http://inference-gateway:8080/v1)
#                              → 按 api_key 路由到 vllm-{role}
#
# api_key 由环境变量注入（由 docker-compose 提供），格式：
#   INFERENCE_API_KEYS  → JSON 字典，如 {"chat":"ak_pool_001","intent":"ak_pool_002"}
#
# 也可单独设置某个角色的 key：
#   INFERENCE_API_KEY_CHAT=ak_pool_001
#   INFERENCE_API_KEY_INTENT=ak_pool_002
#
# 动态运行时配置（本目录下唯一的 YAML 文件）：
#   → roles 段：模型参数（temperature/top_p/max_tokens），与后端无关
#   → chat 段：并发控制（信号量、超时）和多 locale 系统 prompt
#
# 用法：
#   loader = InferenceConfigLoader()
#   result = loader.load_all()
#   engine, entry = loader.get_engine_for_model("chat")
#
#   chat_loader = ChatConfigLoader()
#   configs = chat_loader.load_all()
#   configs["zh_CN"].system_prompt

import json
import os
from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.ai.inference import resolve_engine
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
)
from src.com.damon.ming.app.config._yaml import load_yaml

# ── 连接参数来源：环境变量（由 docker-compose 注入）────────────────────
# INFERENCE_GATEWAY_URL: 推理网关地址，如 http://inference-gateway:8080/v1
# INFERENCE_SERVER:      引擎类型，如 ollama / vllm / sglang
# INFERENCE_TIMEOUT:     超时秒数（可选，默认 180）
# INFERENCE_API_KEYS:    JSON 字典 {role: api_key}（必须覆盖所有角色，否则启动报错）
# INFERANCE_API_KEY_{ROLE}: 单个角色的 api_key（优先级高于 JSON）

# api_key 完全由环境变量注入，不设默认值。
# 未配置的角色在 load_all() 中明确报错。


# ═══════════════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ModelEntry:
    """模型层加载结果。"""

    model_name: str
    options: dict[str, Any]
    api_key: str
    engine_type: str


@dataclass
class ChatLocaleText:
    """单个 locale 的聊天文本配置。"""

    system_prompt: str
    ref_label: str
    query_label: str


class ChatConfig:
    """AI 并发控制配置参数。所有参数无默认值，必须由 YAML 显式提供。"""

    __slots__ = (
        "config_ttl_seconds",
        "guardrail_sem",
        "guardrail_timeout",
        "infer_sem",
        "locale",
        "name",
        "query_label",
        "rag_sem",
        "ref_label",
        "sse_retry_ms",
        "system_prompt",
        "total_timeout",
    )

    def __init__(
        self,
        name: str,
        locale: str,
        system_prompt: str,
        total_timeout: int,
        infer_sem: int,
        rag_sem: int,
        guardrail_sem: int,
        guardrail_timeout: int,
        sse_retry_ms: int,
        config_ttl_seconds: int,
        ref_label: str,
        query_label: str,
    ):
        self.name = name
        self.locale = locale
        self.system_prompt = system_prompt
        self.total_timeout = total_timeout
        self.infer_sem = infer_sem
        self.rag_sem = rag_sem
        self.guardrail_sem = guardrail_sem
        self.guardrail_timeout = guardrail_timeout
        self.sse_retry_ms = sse_retry_ms
        self.config_ttl_seconds = config_ttl_seconds
        self.ref_label = ref_label
        self.query_label = query_label


# common 并发参数的字段名（与 ChatConfig 的 __slots__ 对应）
_COMMON_FIELDS = (
    "config_ttl_seconds",
    "guardrail_sem",
    "guardrail_timeout",
    "infer_sem",
    "rag_sem",
    "sse_retry_ms",
    "total_timeout",
)


# ═══════════════════════════════════════════════════════════════════════
# 环境变量覆盖
# ═══════════════════════════════════════════════════════════════════════


def _resolve_api_keys() -> dict[str, str]:
    """解析各角色的 api_key。

    来源（优先级从高到低）：
      1. INFERENCE_API_KEY_{ROLE} 环境变量（单个角色）
      2. INFERENCE_API_KEYS JSON 环境变量（批量）

    未配置的角色不兜底，由 load_all() 报错。
    """
    keys: dict[str, str] = {}

    # 批量 JSON
    json_str = os.environ.get("INFERENCE_API_KEYS", "")
    if json_str:
        try:
            keys.update(json.loads(json_str))
        except json.JSONDecodeError:
            pass

    # 单个角色（覆盖 JSON + 拾取未在 JSON 中声明的角色）
    for env_key, env_val in os.environ.items():
        prefix = "INFERENCE_API_KEY_"
        if env_key.startswith(prefix) and env_val:
            role = env_key[len(prefix) :].lower()
            keys[role] = env_val

    return keys


# ═══════════════════════════════════════════════════════════════════════
# 推理引擎配置加载器
# ═══════════════════════════════════════════════════════════════════════


class InferenceConfigLoader:
    """连接参数（环境变量） + 运行时配置（YAML）双源合并。

    连接参数由 docker-compose 注入：
      INFERENCE_GATEWAY_URL  → base_url（如 http://inference-gateway:8080/v1）
      INFERENCE_SERVER      → engine_type（如 ollama / vllm / sglang）
      INFERENCE_TIMEOUT     → timeout（可选，默认 180）
      INFERENCE_API_KEYS    → {role: api_key} JSON 字典（必须覆盖所有角色）
    """

    def __init__(self):
        self._engine_type: str = ""
        self._engines: dict[str, BaseInferenceService] = {}
        self._models: dict[str, ModelEntry] = {}
        self._config_dir: str = os.path.dirname(os.path.abspath(__file__))

    def load_all(self) -> dict:
        """一次性加载引擎和模型配置，合并环境变量 + YAML 两个源。"""
        # ── 连接参数：环境变量 ──
        self._engine_type = os.environ.get("INFERENCE_SERVER", "ollama")
        base_url = os.environ.get(
            "INFERENCE_GATEWAY_URL", "http://inference-gateway:8080/v1"
        )
        timeout = float(os.environ.get("INFERENCE_TIMEOUT", "180"))
        api_keys = _resolve_api_keys()

        # ── 模型参数：本目录下 YAML 的 roles 段 ──
        runtime_cfg = load_yaml(self._config_dir)
        if "roles" not in runtime_cfg:
            raise ValueError(f"运行时配置格式错误，缺少 roles: {self._config_dir}")

        params_roles = runtime_cfg["roles"]

        # ── 校验：所有角色必须有 api_key 配置 ──
        missing_roles = [r for r in params_roles if r not in api_keys]
        if missing_roles:
            raise RuntimeError(
                f"以下推理角色缺少 api_key 配置（环境变量 INFERENCE_API_KEY_{{ROLE}} "
                f"或 INFERENCE_API_KEYS JSON）：{', '.join(missing_roles)}"
            )

        # ── 解析引擎类型 ──
        engine_type = self._engine_type
        impl_cls = resolve_engine(engine_type)

        # ── 逐角色创建引擎（不同 api_key → 不同引擎实例）──
        for role, role_params in params_roles.items():
            api_key = api_keys.get(role, "")

            # api_key 相同的角色共享引擎（如 guardrail 复用 intent）
            engine_key = api_key or "__shared__"
            if engine_key not in self._engines:
                params = InferenceParams(
                    base_url=base_url,
                    timeout=timeout,
                    api_key=api_key,
                )
                self._engines[engine_key] = impl_cls(params)

            # 模型参数来自 inference-runtime.yaml
            options = dict(role_params.items())

            self._models[role] = ModelEntry(
                model_name=role,  # 网关模式下 model 由 gateway 注入，这里用 role 占位
                options=options,
                api_key=api_key,
                engine_type=engine_type,
            )

        return {
            "engines": self._engines,
            "models": self._models,
        }

    def get_engine_for_model(
        self, role: str = "chat"
    ) -> tuple[BaseInferenceService, ModelEntry]:
        """获取引擎实例和指定角色的模型信息。"""
        if not self._models:
            self.load_all()
        entry = self._models[role]
        engine_key = entry.api_key or "__shared__"
        engine = self._engines[engine_key]
        return engine, entry


# ═══════════════════════════════════════════════════════════════════════
# 聊天并发配置加载器
# ═══════════════════════════════════════════════════════════════════════


class ChatConfigLoader:
    """从 inference-runtime.yaml 的 chat 段加载并发控制配置。

    用法：
        loader = ChatConfigLoader()
        configs = loader.load_all()
        configs["zh_CN"].system_prompt   # locale 配置（含并发参数）
        configs["en_US"].infer_sem       # 从 common 继承的并发参数
    """

    def __init__(self):
        self._cache: dict[str, ChatConfig] = {}
        self._cache_loaded_at: float = 0.0
        self._cache_ttl_seconds: float = 0.0
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load_all(self) -> dict[str, ChatConfig]:
        """加载所有 locale 配置，每个配置已合并 common 并发参数。"""
        import time

        now = time.monotonic()
        if self._cache and (now - self._cache_loaded_at) < self._cache_ttl_seconds:
            return self._cache
        self._cache.clear()

        raw = self._read_yaml()
        common = self._load_common(raw)

        for locale in self._list_locale_profiles(raw):
            self._cache[locale] = self._build_locale(locale, common, raw)

        self._cache_loaded_at = now
        return self._cache

    def load(self, locale: str) -> ChatConfig:
        """加载指定 locale 的配置。"""
        import time

        now = time.monotonic()
        if self._cache and (now - self._cache_loaded_at) < self._cache_ttl_seconds:
            return self._cache[locale]

        raw = self._read_yaml()
        common = self._load_common(raw)
        config = self._build_locale(locale, common, raw)
        self._cache[locale] = config
        self._cache_loaded_at = now
        return config

    # ---- 静态工具方法 ---------------------------------------------------

    @staticmethod
    def resolve_locale_text(
        chat_locales: dict[str, ChatLocaleText], locale: str
    ) -> ChatLocaleText:
        """根据 locale 选择聊天文本配置，回退到 zh_CN。"""
        cfg = chat_locales.get(locale)
        if cfg is None:
            cfg = chat_locales["zh_CN"]
        return cfg

    # ---- 私有 ---------------------------------------------------------

    def _load_common(self, raw: dict) -> dict:
        """从 chat.common 段提取并发参数字典。"""
        if "chat" not in raw or "common" not in raw["chat"]:
            raise ValueError("配置文件格式错误：缺少 chat.common 根节点")
        common_section = raw["chat"]["common"]
        # TTL 每次构建时刷新
        self._cache_ttl_seconds = float(common_section.get("config_ttl_seconds", 60))
        try:
            pipeline = common_section["pipeline"]
            return {
                "total_timeout": int(pipeline["total_timeout"]),
                "infer_sem": int(pipeline["inference"]["semaphore"]),
                "rag_sem": int(pipeline["rag"]["semaphore"]),
                "guardrail_sem": int(common_section["guardrail"]["semaphore"]),
                "guardrail_timeout": int(common_section["guardrail"]["timeout"]),
                "sse_retry_ms": int(common_section["sse_retry_ms"]),
                "config_ttl_seconds": int(common_section.get("config_ttl_seconds", 60)),
            }
        except KeyError as e:
            raise ValueError(f"common 缺少必填字段: {e}") from e

    def _list_locale_profiles(self, raw: dict) -> list[str]:
        """列出 chat.locales 下所有 locale 段。"""
        if "chat" not in raw:
            raise ValueError("配置文件格式错误：缺少 'chat' 根节点")
        if "locales" not in raw["chat"]:
            raise ValueError("配置文件格式错误：缺少 chat.locales 节点")
        return list(raw["chat"]["locales"].keys())

    def _build_locale(self, locale: str, common: dict, raw: dict) -> ChatConfig:
        """构建单个 locale 配置，合并 common 并发参数 + locale 文本。"""
        section = raw["chat"]["locales"].get(locale, {})
        if not section:
            raise ValueError(f"配置文件中未找到 locale 段: {locale}")
        try:
            return ChatConfig(
                name=locale,
                locale=locale,
                system_prompt=section["system_prompt"],
                ref_label=str(section["ref_label"]),
                query_label=str(section["query_label"]),
                total_timeout=common["total_timeout"],
                infer_sem=common["infer_sem"],
                rag_sem=common["rag_sem"],
                guardrail_sem=common["guardrail_sem"],
                guardrail_timeout=common["guardrail_timeout"],
                sse_retry_ms=common["sse_retry_ms"],
                config_ttl_seconds=common["config_ttl_seconds"],
            )
        except KeyError as e:
            raise ValueError(f"locale '{locale}' 缺少必填字段: {e}") from e

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)
