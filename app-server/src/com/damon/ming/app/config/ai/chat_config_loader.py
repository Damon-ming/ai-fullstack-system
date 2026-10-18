# app-server/src/com/damon/ming/app/config/ai/chat_config_loader.py
"""
AI 并发控制配置加载器 —— 从 YAML 读取 Semaphore 参数、超时、系统 prompt。

本模块属于 app/config/ai/ 配置层，不属于 chat 模块。
chat_router 通过 ChatConfig 数据类接收参数，不感知配置来源。

加载失败（文件不存在、格式错误、剖面缺失）直接抛出异常。
"""

import os

import yaml


class ChatConfig:
    """AI 并发控制配置参数。所有参数无默认值，必须由 YAML 显式提供。"""

    __slots__ = (
        "config_ttl_seconds",
        "guardrail_sem",
        "guardrail_timeout",
        "infer_sem",
        "name",
        "rag_sem",
        "sse_retry_ms",
        "system_prompt",
        "total_timeout",
    )

    def __init__(
        self,
        name: str,
        system_prompt: str,
        total_timeout: int,
        infer_sem: int,
        rag_sem: int,
        guardrail_sem: int,
        guardrail_timeout: int,
        sse_retry_ms: int,
        config_ttl_seconds: int,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.total_timeout = total_timeout
        self.infer_sem = infer_sem
        self.rag_sem = rag_sem
        self.guardrail_sem = guardrail_sem
        self.guardrail_timeout = guardrail_timeout
        self.sse_retry_ms = sse_retry_ms
        self.config_ttl_seconds = config_ttl_seconds


class ChatConfigLoader:
    """从 YAML 文件加载 AI 并发控制配置。

    用法：
        loader = ChatConfigLoader()
        configs = loader.load_all()
        configs["common"].infer_sem
    """

    def __init__(self, config_path: str | None = None):
        self._cache: dict[str, ChatConfig] = {}
        self._cache_loaded_at: float = 0.0
        self._cache_ttl_seconds: float = 0.0  # 由 _build_one() 首次加载时设置
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "chat-config.yaml")
        self._config_path = config_path

    def load_all(self) -> dict[str, ChatConfig]:
        import time

        now = time.monotonic()
        if self._cache and (now - self._cache_loaded_at) < self._cache_ttl_seconds:
            return self._cache
        self._cache.clear()
        for name in self._list_profiles():
            self._cache[name] = self._build_one(name)
        self._cache_loaded_at = now
        return self._cache

    def load(self, name: str) -> ChatConfig:
        import time

        now = time.monotonic()
        if self._cache and (now - self._cache_loaded_at) < self._cache_ttl_seconds:
            return self._cache[name]
        config = self._build_one(name)
        self._cache[name] = config
        self._cache_loaded_at = now
        return config

    # ---- 私有 -------------------------------------------------------------

    def _list_profiles(self) -> list[str]:
        raw = self._read_yaml()
        if "chat" not in raw:
            raise ValueError("配置文件格式错误：缺少 'chat' 根节点")
        return list(raw["chat"].keys())

    def _build_one(self, name: str) -> ChatConfig:
        raw = self._read_yaml()
        section = raw["chat"].get(name, {})
        if not section:
            raise ValueError(f"配置文件中未找到剖面: {name}")
        # TTL 每次构建时刷新（config_ttl_seconds 变化后下次缓存过期即生效）
        self._cache_ttl_seconds = float(section.get("config_ttl_seconds", 60))
        try:
            pipeline = section["pipeline"]
            return ChatConfig(
                name=name,
                system_prompt=section["system_prompt"],
                total_timeout=int(pipeline["total_timeout"]),
                infer_sem=int(pipeline["inference"]["semaphore"]),
                rag_sem=int(pipeline["rag"]["semaphore"]),
                guardrail_sem=int(section["guardrail"]["semaphore"]),
                guardrail_timeout=int(section["guardrail"]["timeout"]),
                sse_retry_ms=int(section["sse_retry_ms"]),
                config_ttl_seconds=int(section.get("config_ttl_seconds", 60)),
            )
        except KeyError as e:
            raise ValueError(f"配置 '{name}' 缺少必填字段: {e}") from e

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None:
            raise ValueError("配置文件为空")
        return raw_cfg
