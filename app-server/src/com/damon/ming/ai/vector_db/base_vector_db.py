# app-server/src/com/damon/ming/ai/vector_db/base_vector_db.py
"""
向量存储抽象层 —— 纯技术模块，零业务逻辑，可独立移植。

设计模式与 db/ 模块一致：
  - BaseVectorStore:  抽象接口（所有 vector_db 实现的契约）
  - VectorStoreParams: 纯数据类，组合公共参数与引擎参数

不提供：
  - 配置加载 → 见 ai/vector_db/config/vector_config_loader.py
  - 具体实现 → 见 chroma_store.py / pgvector_store.py

用法：
  from src.com.damon.ming.ai.vector_db import BaseVectorStore, VectorStoreParams
  from src.com.damon.ming.ai.vector_db.chroma_store import ChromaDBStore
  from src.com.damon.ming.ai.vector_db.pgvector_store import PGVectorStore

  params = VectorStoreParams(
      shared_params=SharedVectorStoreParams(
          table_name="rag_documents", embedding_dimension=1024
      ),
      engine_params=PGVectorParams(...),
  )
  store = PGVectorStore(params)
  nodes = store.similarity_search_by_vector(query_vector, k=4)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from llama_index.core.schema import TextNode

# ── 参数数据类 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SharedVectorStoreParams:
    """所有向量存储共用的参数。table_name 对 Chroma 表示 collection 名。"""

    table_name: str
    embedding_dimension: int


@dataclass(frozen=True)
class PGVectorParams:
    """PGVector 专属配置。"""

    connection_string: str
    pool_min_conn: int
    pool_max_conn: int
    pool_recycle: int
    hnsw_m: int
    hnsw_ef_construction: int


@dataclass(frozen=True)
class ChromaParams:
    """Chroma 专属配置。"""

    persist_directory: str
    host: str = ""
    port: int = 0


@dataclass(frozen=True)
class VectorStoreParams:
    """公共参数与所选向量引擎的专属参数。"""

    shared_params: SharedVectorStoreParams
    engine_params: PGVectorParams | ChromaParams


# ── 抽象接口 ──────────────────────────────────────────────────────


class BaseVectorStore(ABC):
    """
    向量存储抽象基类。

    异常行为规范（所有实现类必须遵守）：
      add_documents           → 失败抛 Exception
      similarity_search_by_vector → 失败返回 []
      delete_by_metadata      → 默认失败返回 0；PGVector 实现覆盖为抛 RuntimeError
      get_by_metadata         → 失败返回 []
      count                   → 失败返回 0
      close                   → 幂等不抛异常
    """

    def __init__(self, params: VectorStoreParams):
        self.params = params

    @abstractmethod
    def add_documents(self, nodes: list[TextNode], **kwargs) -> list[str]:
        """添加文档，失败抛 Exception"""
        ...

    @abstractmethod
    def similarity_search_by_vector(
        self,
        query_vector: list[float],
        k: int,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        """向量相似度检索，失败返回 []"""
        ...

    @abstractmethod
    def delete_by_metadata(self, metadata_filter: dict[str, Any], **kwargs) -> int:
        """根据元数据删除文档，返回删除数量。

        默认契约：失败返回 0。
        PGVector 实现覆盖为失败抛 RuntimeError，确保调用方可感知。
        调用方应按需 try/except RuntimeError 处理。
        """
        ...

    @abstractmethod
    def get_by_metadata(
        self, metadata_filter: dict[str, Any], **kwargs
    ) -> list[TextNode]:
        """根据元数据查询，失败返回 []"""
        ...

    @abstractmethod
    def get_by_metadata_batch(
        self,
        filters: list[dict[str, Any]],
        **kwargs,
    ) -> list[TextNode]:
        """批量元数据查询（OR 语义：匹配任意一个 filter 的文档）。

        默认实现：逐个调用 get_by_metadata 后合并。
        具体实现可覆盖为原生批量查询（如 pgvector 的 OR 条件合并），减少数据库扫描次数。
        """
        ...

    @abstractmethod
    def get_distinct_metadata_values(self, key: str) -> set[str] | None:
        """返回指定 metadata 字段的非空字符串集合；查询失败返回 None。"""
        ...

    @abstractmethod
    def update_metadata_by_filter(
        self,
        metadata_filter: dict[str, Any],
        updates: dict[str, Any] | None = None,
        remove_keys: set[str] | None = None,
    ) -> int:
        """更新匹配节点的 metadata，返回受影响节点数；失败抛异常。"""
        ...

    @abstractmethod
    def count(self, **kwargs) -> int:
        """获取文档总数，失败返回 0"""
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭连接/释放资源，幂等"""
        ...
