# app-server/src/com/damon/ming/app/config/ai/chat_config_loader.py
"""
AI 并发控制配置加载器 —— 从 YAML 读取 Semaphore 参数、超时、系统 prompt。

本模块属于 app/config/ai/ 配置层，不属于 chat 模块。
chat_router 通过 ChatConfig 数据类接收参数，不感知配置来源。

配置结构：
  common          —— 并发参数（信号量、超时），所有 locale 共享
  zh_CN / en_US   —— locale 特有的 LLM 指令文本（ref_label, query_label, system_prompt）
  构建 locale config 时，自动从 common 继承并发参数。

加载失败（文件不存在、格式错误、剖面缺失）直接抛出异常。
"""

import os
from dataclasses import dataclass

import yaml


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


class ChatConfigLoader:
    """从 YAML 文件加载 AI 并发控制配置。

    用法：
        loader = ChatConfigLoader()
        configs = loader.load_all()
        configs["zh_CN"].system_prompt   # locale 配置（含并发参数）
        configs["en_US"].infer_sem       # 从 common 继承的并发参数
    """

    def __init__(self, config_path: str | None = None):
        self._cache: dict[str, ChatConfig] = {}
        self._cache_loaded_at: float = 0.0
        self._cache_ttl_seconds: float = 0.0  # 首次加载时从 common 设置
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "chat-config.yaml")
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

    # ---- 私有 -------------------------------------------------------------

    def _load_common(self, raw: dict) -> dict:
        """从 common 段提取并发参数字典。"""
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
        """列出 locales 下所有 locale 段。"""
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

    @staticmethod
    def resolve_locale_text(
        chat_locales: dict[str, ChatLocaleText], locale: str
    ) -> ChatLocaleText:
        """根据 locale 选择聊天文本配置，回退到 zh_CN。"""
        cfg = chat_locales.get(locale)
        if cfg is None:
            cfg = chat_locales["zh_CN"]
        return cfg

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None:
            raise ValueError("配置文件为空")
        return raw_cfg
