"""Configuration contract for RAG-owned thread pools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class RagThreadPoolConfig:
    workers: dict[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.workers, dict) or not self.workers:
            raise ValueError("RAG thread_pools 配置必须是非空键值对象")
        for name, count in self.workers.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("RAG 线程池名称必须是非空字符串")
            if type(count) is not int or count <= 0:
                raise ValueError(f"RAG 线程池 {name} 的 worker 数必须是正整数")
        missing = {"retrieval", "document", "rerank", "bm25"} - self.workers.keys()
        if missing:
            raise ValueError(
                f"RAG thread_pools 缺少线程池: {', '.join(sorted(missing))}"
            )

    @classmethod
    def from_mapping(cls, raw: Any) -> RagThreadPoolConfig:
        if not isinstance(raw, dict):
            raise TypeError("RAG thread_pools 配置必须是非空键值对象")
        return cls(workers=raw)
