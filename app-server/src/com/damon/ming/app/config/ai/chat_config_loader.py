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
        "guardrail_sem",
        "guardrail_timeout",
        "infer_sem",
        "infer_timeout",
        "name",
        "rag_sem",
        "retry_ms",
        "system_prompt",
    )

    def __init__(
        self,
        name: str,
        system_prompt: str,
        infer_sem: int,
        rag_sem: int,
        guardrail_sem: int,
        guardrail_timeout: int,
        infer_timeout: int,
        retry_ms: int,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.infer_sem = infer_sem
        self.rag_sem = rag_sem
        self.guardrail_sem = guardrail_sem
        self.guardrail_timeout = guardrail_timeout
        self.infer_timeout = infer_timeout
        self.retry_ms = retry_ms


class ChatConfigLoader:
    """从 YAML 文件加载 AI 并发控制配置。

    用法：
        loader = ChatConfigLoader()
        configs = loader.load_all()
        configs["common"].infer_sem
    """

    def __init__(self, config_path: str | None = None):
        self._cache: dict[str, ChatConfig] = {}
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "chat-config.yaml")
        self._config_path = config_path

    def load_all(self) -> dict[str, ChatConfig]:
        if self._cache:
            return self._cache
        for name in self._list_profiles():
            self._cache[name] = self._build_one(name)
        return self._cache

    def load(self, name: str) -> ChatConfig:
        if name in self._cache:
            return self._cache[name]
        config = self._build_one(name)
        self._cache[name] = config
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
        try:
            return ChatConfig(
                name=name,
                system_prompt=section["system_prompt"],
                infer_sem=int(section["inference"]["semaphore"]),
                infer_timeout=int(section["inference"]["timeout"]),
                rag_sem=int(section["rag"]["semaphore"]),
                guardrail_sem=int(section["guardrail"]["semaphore"]),
                guardrail_timeout=int(section["guardrail"]["timeout"]),
                retry_ms=int(section["retry_ms"]),
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
