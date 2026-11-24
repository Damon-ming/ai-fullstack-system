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
from pathlib import Path

from src.com.damon.ming.ai.rag.tokenizer import resolve_tokenizer
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import (
    JiebaTokenizerParams,
    TiktokenTokenizerParams,
)
from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class TokenizerConfigLoader:
    """从 YAML 文件加载分词器配置，返回 BaseTokenizer / BaseWordTokenizer 实例。

    启动时全量加载，所有分词器在服务启动阶段初始化完毕。
    """

    def __init__(self, config_path: str | None = None):
        self._config_path = resolve_yaml_path(
            config_path if config_path is not None else os.path.dirname(__file__)
        )
        self._cache: dict[str, object] = {}

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
            name: 配置文件顶层的 tokenizer 实例名

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
        return list(raw_cfg.keys())

    def _build_one(self, name: str):
        raw = self._read_yaml(name)
        engine = raw.get("tokenizer_engine")
        if not engine:
            raise ValueError("配置缺少 tokenizer_engine 字段")

        params_raw = raw.get("params", {})
        if not isinstance(params_raw, dict):
            raise TypeError(f"分词器 '{name}' 的 params 必须是键值对象")

        if engine == "tiktoken":
            encoding_name = params_raw.get("encoding_name")
            if not isinstance(encoding_name, str) or not encoding_name.strip():
                raise ValueError(f"分词器 '{name}' 缺少有效的 params.encoding_name")
            params = TiktokenTokenizerParams(encoding_name=encoding_name)
        elif engine == "jieba":
            params = JiebaTokenizerParams(
                user_dict_paths=self._discover_jieba_dict_paths(params_raw, name)
            )
        else:
            raise ValueError(f"分词器引擎 '{engine}' 尚未配置对应的参数解析器")

        tokenizer_class = resolve_tokenizer(engine)

        return tokenizer_class(params)

    def _discover_jieba_dict_paths(self, params: dict, name: str) -> tuple[str, ...]:
        """查找 tokenizer/ 下词典目录中的全部 .txt 文件。"""
        dicts_dir_name = params.get("dicts_dir")
        if dicts_dir_name is None or dicts_dir_name == "":
            return ()
        if not isinstance(dicts_dir_name, str):
            raise TypeError(f"分词器 '{name}' 的 params.dicts_dir 必须是字符串")
        dicts_dir_name = dicts_dir_name.strip()
        if not dicts_dir_name:
            return ()

        tokenizer_dir = Path(__file__).resolve().parent.parent
        dicts_dir = (tokenizer_dir / dicts_dir_name).resolve()
        if not dicts_dir.is_dir():
            raise FileNotFoundError(f"分词器 '{name}' 的词典目录不存在: {dicts_dir}")

        return tuple(
            str(path.resolve())
            for path in sorted(dicts_dir.glob("*.txt"))
            if path.is_file()
        )

    def _read_yaml(self, name: str) -> dict:
        raw_cfg = load_yaml(self._config_path)

        if name not in raw_cfg:
            raise ValueError(
                f"未找到分词器配置: '{name}'. 可用: {list(raw_cfg.keys())}"
            )
        section = raw_cfg[name]
        if not isinstance(section, dict):
            raise TypeError(f"分词器配置 '{name}' 必须是键值对象")
        return section
