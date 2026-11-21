# app-server/src/com/damon/ming/ai/rag/tokenizer/config/tokenizer_config_loader.py
"""
分词器配置加载器 —— 从 YAML 读取引擎名称和参数，构造 TokenizerParams。

本模块属于 tokenizer/ 配置层。
tokenizer/ 实现通过 TokenizerParams 数据类接收参数。

启动时通过 load_all() 一次性加载全部配置实例，避免懒加载导致的响应延迟。

用法：
  loader = TokenizerConfigLoader()
  tokenizers = loader.load_all()                # dict[str, BaseTokenizer]
  tokenizers["llm_counter"].count_tokens(...)
  tokenizers["bm25_searcher"].tokenize(...)
"""

import os

from src.com.damon.ming.ai.rag.tokenizer import resolve_tokenizer
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import TokenizerParams
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class TokenizerConfigLoader:
    """从 YAML 文件加载分词器配置，返回 BaseTokenizer / BaseWordTokenizer 实例。

    启动时全量加载，所有分词器在服务启动阶段初始化完毕。
    """

    _cache: dict[str, object] = {}

    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )

    def load_all(self) -> dict[str, object]:
        """一次性加载 YAML 中所有配置的分词器实例。

        Returns:
            dict[配置名, BaseTokenizer / BaseWordTokenizer 实例]
        """
        if self._cache:
            return self._cache

        for name in self._list_names():
            self._cache[name] = self._build_one(name)
        return self._cache

    def load(self, name: str):
        """加载指定名称的分词器，未缓存则构建。

        Args:
            name: tokenizers 下的键名

        Returns:
            BaseTokenizer 或 BaseWordTokenizer 实例
        """
        if name in self._cache:
            return self._cache[name]

        instance = self._build_one(name)
        self._cache[name] = instance
        return instance

    # ---- 私有 -------------------------------------------------------------

    def _list_names(self) -> list[str]:
        raw_cfg = load_yaml(self._config_path)
        if raw_cfg is None or "tokenizers" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'tokenizers' 根节点")
        return list(raw_cfg["tokenizers"].keys())

    def _build_one(self, name: str):
        raw = self._read_yaml(name)
        params_raw = raw.get("params", {})

        known_fields = {f.name for f in TokenizerParams.__dataclass_fields__.values()}
        base_kwargs = {k: v for k, v in params_raw.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in params_raw.items() if k not in known_fields}

        # 将 dicts_base_dir 相对路径解析为绝对路径（锚定 tokenizer-config.yaml 位置）
        if base_kwargs.get("dicts_base_dir") and not os.path.isabs(
            base_kwargs["dicts_base_dir"]
        ):
            config_dir = os.path.dirname(os.path.abspath(self._config_path))
            src_root = os.path.abspath(
                os.path.join(config_dir, "..", "..", "..", "..", "..", "..", "..")
            )
            base_kwargs["dicts_base_dir"] = os.path.abspath(
                os.path.join(src_root, base_kwargs["dicts_base_dir"])
            )

        params = TokenizerParams(**base_kwargs, extra=extra_kwargs)

        engine = raw.get("tokenizer_engine")
        if not engine:
            raise ValueError("配置缺少 tokenizer_engine 字段")
        tokenizer_class = resolve_tokenizer(engine)

        return tokenizer_class(params)

    def _read_yaml(self, name: str) -> dict:
        raw_cfg = load_yaml(self._config_path)

        if raw_cfg is None or "tokenizers" not in raw_cfg:
            raise ValueError("配置文件格式错误：缺少 'tokenizers' 根节点")

        section = raw_cfg["tokenizers"]
        if name not in section:
            raise ValueError(
                f"未找到分词器配置: '{name}'. 可用: {list(section.keys())}"
            )
        return section[name]
