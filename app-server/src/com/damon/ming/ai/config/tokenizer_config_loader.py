# app-server/src/com/damon/ming/ai/config/tokenizer_config_loader.py
"""
分词器配置加载器 —— 从 YAML 读取引擎名称和参数，构造 TokenizerParams。

本模块属于 ai/config/ 配置层，不属于 tokenizer/ 模块。
tokenizer/ 模块通过 TokenizerParams 数据类接收参数，不感知配置来源。

支持多个分词器实例同时存在（如 token ID 级 + 词语级），各组件按需选用。

用法：
  loader = TokenizerConfigLoader()
  tokenizer = loader.load("llm_counter")         # Token ID 级
  bm25_tokenizer = loader.load("bm25_searcher")   # 词语级
"""

import os

import yaml
from src.com.damon.ming.ai.tokenizer import resolve_tokenizer
from src.com.damon.ming.ai.tokenizer.base_tokenizer import TokenizerParams


class TokenizerConfigLoader:
    """从 YAML 文件加载分词器配置，返回 BaseTokenizer / BaseWordTokenizer 实例。

    同名分词器缓存复用，避免重复加载（如 jieba 词典只加载一次）。
    """

    _cache: dict[str, object] = {}

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "tokenizer-config.yaml")
        self._config_path = config_path

    def load(self, name: str):
        """加载指定名称的分词器配置，同名返回缓存实例。

        Args:
            name: tokenizers 下的键名，如 "llm_counter" / "bm25_searcher"

        Returns:
            BaseTokenizer 或 BaseWordTokenizer 实例
        """
        if name in self._cache:
            return self._cache[name]

        raw = self._read_yaml(name)
        params_raw = raw.get("params", {})

        known_fields = {f.name for f in TokenizerParams.__dataclass_fields__.values()}
        base_kwargs = {k: v for k, v in params_raw.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in params_raw.items() if k not in known_fields}
        params = TokenizerParams(**base_kwargs, extra=extra_kwargs)

        engine = raw.get("tokenizer_engine")
        if not engine:
            raise ValueError("配置缺少 tokenizer_engine 字段")
        tokenizer_class = resolve_tokenizer(engine)

        instance = tokenizer_class(params)
        self._cache[name] = instance
        return instance

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self, name: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"分词器配置文件不存在: {self._config_path}")

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)

        if raw_cfg is None or "tokenizers" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'tokenizers' 根节点")

        section = raw_cfg["tokenizers"]
        if name not in section:
            raise ValueError(
                f"未找到分词器配置: '{name}'. 可用: {list(section.keys())}"
            )
        return section[name]
