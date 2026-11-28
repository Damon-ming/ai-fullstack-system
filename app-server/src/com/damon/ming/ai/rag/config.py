"""RAG 编排配置及子模块配置段的读取与结构校验。"""

from __future__ import annotations

from typing import Any


class RagModuleConfig:
    """只分发原始配置段，具体字段由各子模块解析和校验。"""

    def __init__(self, raw: Any) -> None:
        if not isinstance(raw, dict):
            raise TypeError("RagChoreographer 配置必须是键值对象")
        self._sections: dict[str, dict[str, Any]] = {}
        for name in (
            "thread_pools",
            "constructor",
            "rerank",
            "retriever",
            "splitter",
            "summary",
            "source",
            "tokenizer",
        ):
            section = raw.get(name)
            if not isinstance(section, dict):
                raise TypeError(f"RagChoreographer 配置缺少有效的 {name} 段")
            self._sections[name] = section

    def get_thread_pool_config(self) -> dict[str, Any]:
        return self._sections["thread_pools"]

    def get_constructor_config(self) -> dict[str, Any]:
        return self._sections["constructor"]

    def get_reranker_config(self) -> dict[str, Any]:
        return self._sections["rerank"]

    def get_retriever_config(self) -> dict[str, Any]:
        return self._sections["retriever"]

    def get_splitter_config(self) -> dict[str, Any]:
        return self._sections["splitter"]

    def get_summary_config(self) -> dict[str, Any]:
        return self._sections["summary"]

    def get_source_config(self) -> dict[str, Any]:
        return self._sections["source"]

    def get_tokenizer_config(self) -> dict[str, Any]:
        return self._sections["tokenizer"]
