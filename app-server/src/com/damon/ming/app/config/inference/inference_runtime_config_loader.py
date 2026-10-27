# 推理运行时配置加载器 —— 双源合并 + 聊天并发控制。
#
# 配置分为两层：
#   1. 静态连接：config/connections/{engine}.yaml（base_url / api_key / timeout / engine）
#      -> 引擎选择由 INFERENCE_SERVER 环境变量决定，部署时固定
#   2. 动态运行时：inference-runtime.yaml（与本加载器同级）
#      -> roles 段：模型参数（temperature/top_p/max_tokens），与后端无关
#      -> chat 段：并发控制（信号量、超时）和多 locale 系统 prompt
#      -> 可按业务场景（profile）动态调整，请求时读取
#
# 文件布局：
#   app-server/config/                      ← 静态部署配置（connections/docker/gateway）
#   app/config/inference/inference-runtime.yaml  ← 动态运行时配置（本文件同级）
#   app/config/inference/inference_runtime_config_loader.py  ← 本加载器
#
# 合并逻辑：
#   engine 类型取自 INFERENCE_SERVER 环境变量 -> config/connections/{engine}.yaml
#   base_url、timeout、api_key、model 取自连接配置
#   temperature、top_p、max_tokens 取自 inference-runtime.yaml roles 段
#
# 用法：
#   loader = InferenceConfigLoader()
#   result = loader.load_all()
#   engine, entry = loader.get_engine_for_model("chat")
#
#   chat_loader = ChatConfigLoader()
#   configs = chat_loader.load_all()
#   configs["zh_CN"].system_prompt

import os
from dataclasses import dataclass
from typing import Any

import yaml
from src.com.damon.ming.ai.inference import resolve_engine
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
)

# ── 静态部署配置根目录（app-server/config/）────────────────────────────
# connections/docker/gateway 等部署时固定的配置
_STATIC_CONFIG_ROOT = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "..",
        "..",
        "..",
        "config",
    )
)

# ── 连接配置目录 ──────────────────────────────────────────────────────
_CONNECTIONS_DIR = os.path.join(_STATIC_CONFIG_ROOT, "connections")

# ── 动态运行时配置（与本加载器同级，可按业务动态调整）────────────────
_RUNTIME_CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "inference-runtime.yaml")
)

# ── 环境变量覆盖模式 ──────────────────────────────────────────────────
# CHAT_TEMPERATURE=0.5  -> 覆盖 chat 角色的 temperature
# 格式：{ROLE_UPPER}_{PARAM}


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


def _apply_env_overrides(role: str, options: dict[str, Any]) -> dict[str, Any]:
    """应用环境变量覆盖（格式：{ROLE_UPPER}_{PARAM}）。"""
    result = dict(options)
    role_upper = role.upper()
    for param in ("temperature", "top_p", "max_tokens"):
        env_key = f"{role_upper}_{param.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            # 尝试保持原类型
            original_type = type(options[param])
            try:
                result[param] = original_type(env_val)
            except (ValueError, TypeError):
                result[param] = env_val
    return result


# ═══════════════════════════════════════════════════════════════════════
# 推理引擎配置加载器
# ═══════════════════════════════════════════════════════════════════════


class InferenceConfigLoader:
    """双源合并：config/connections/{engine}.yaml（连接） + inference-runtime.yaml（模型参数）。"""

    def __init__(self):
        self._engine_type: str = ""
        self._engines: dict[str, BaseInferenceService] = {}
        self._models: dict[str, ModelEntry] = {}

    def load_all(self) -> dict:
        """一次性加载引擎和模型配置，合并两个 YAML 源。"""
        # ── 确定引擎类型和连接配置路径 ──
        self._engine_type = os.environ.get("INFERENCE_SERVER", "ollama")
        conn_path = os.path.join(_CONNECTIONS_DIR, f"{self._engine_type}.yaml")

        if not os.path.exists(conn_path):
            raise FileNotFoundError(
                f"连接配置不存在: {conn_path}（INFERENCE_SERVER={self._engine_type}）"
            )

        # ── 读取连接配置 ──
        with open(conn_path, "r", encoding="utf-8") as f:
            conn_cfg = yaml.safe_load(f)

        if not conn_cfg or "roles" not in conn_cfg:
            raise ValueError(f"连接配置格式错误，缺少 roles: {conn_path}")

        # ── 读取模型参数（inference-runtime.yaml 的 roles 段）──
        if not os.path.exists(_RUNTIME_CONFIG_PATH):
            raise FileNotFoundError(f"运行时配置不存在: {_RUNTIME_CONFIG_PATH}")

        with open(_RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
            runtime_cfg = yaml.safe_load(f)

        if not runtime_cfg or "roles" not in runtime_cfg:
            raise ValueError(f"运行时配置格式错误，缺少 roles: {_RUNTIME_CONFIG_PATH}")

        params_roles = runtime_cfg["roles"]

        # ── 解析引擎类型 ──
        # 优先取 YAML 中的 engine 字段，其次用 INFERENCE_SERVER 环境变量
        engine_type = conn_cfg.get("engine") or self._engine_type
        self._engine_type = engine_type
        base_url = conn_cfg.get("base_url", "")
        timeout = conn_cfg.get("default_timeout", 180)
        impl_cls = resolve_engine(engine_type)

        # ── 逐角色合并 ──
        for role, role_conn in conn_cfg["roles"].items():
            if role not in params_roles:
                raise ValueError(
                    f"连接配置中的角色 '{role}' 在运行时配置中缺少对应参数"
                )

            api_key = role_conn.get("api_key", "")
            model_name = role_conn.get("model", "")

            # api_key 为空时（如 Ollama），共享引擎
            engine_key = api_key or "__shared__"
            if engine_key not in self._engines:
                params = InferenceParams(
                    base_url=base_url,
                    timeout=timeout,
                    api_key=api_key,
                )
                self._engines[engine_key] = impl_cls(params)

            # 模型参数来自 inference-runtime.yaml + 环境变量覆盖
            raw_options = {k: v for k, v in params_roles[role].items()}
            options = _apply_env_overrides(role, raw_options)

            self._models[role] = ModelEntry(
                model_name=model_name,
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

    def __init__(self, config_path: str | None = None):
        self._cache: dict[str, ChatConfig] = {}
        self._cache_loaded_at: float = 0.0
        self._cache_ttl_seconds: float = 0.0
        if config_path is None:
            config_path = _RUNTIME_CONFIG_PATH
        self._config_path = config_path

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
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None:
            raise ValueError("配置文件为空")
        return raw_cfg
