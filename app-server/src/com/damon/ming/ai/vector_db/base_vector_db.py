# app-server/src/com/damon/ming/ai/vector_db/base_vector_db.py
"""
向量存储抽象层 —— 纯技术模块，零业务逻辑，可独立移植。

设计模式与 db/ 模块一致：
  - BaseVectorStore:  抽象接口（所有 vector_db 实现的契约）
  - VectorStoreParams: 纯数据类，参数由上层配置注入，本模块不感知配置来源

不提供：
  - 配置加载 → 见 ai/config/vector_config_loader.py
  - 具体实现 → 见 chroma_store.py / pgvector_store.py

用法：
  from src.com.damon.ming.ai.vector_db import BaseVectorStore, VectorStoreParams
  from src.com.damon.ming.ai.vector_db.chroma_store import ChromaDBStore
  from src.com.damon.ming.ai.vector_db.pgvector_store import PGVectorStore

  params = VectorStoreParams(connection_string="postgresql://...", embedding_dimension=1024)
  store = PGVectorStore(params)
  nodes = store.similarity_search_by_vector(query_vector, k=4)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from llama_index.core.schema import TextNode

# ── 参数数据类 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class VectorStoreParams:
    """向量存储连接参数（纯数据类）。

    所有参数由上层配置传入，vector_db 模块内不含任何 YAML/环境变量读取逻辑。
    关键决策参数无默认值，必须在 YAML 中显式声明。
    """

    # ---- 全部无默认值，由 YAML 显式注入 ----
    # ChromaDB
    collection_name: str
    persist_directory: str
    host: str
    port: int
    # PGVector
    connection_string: str
    table_name: str
    pool_min_conn: int
    pool_max_conn: int
    hnsw_m: int
    hnsw_ef_construction: int
    # 通用
    embedding_dimension: int

    # ---- 扩展（各实现特有参数透传）----
    extra: dict[str, Any] = field(default_factory=dict)


# ── 抽象接口 ──────────────────────────────────────────────────────


class BaseVectorStore(ABC):
    """
    向量存储抽象基类。

    异常行为规范（所有实现类必须遵守）：
      add_documents           → 失败抛 Exception
      delete / clear          → 失败返回 False
      similarity_search       → 失败抛 NotImplementedError（不支持文本直查）
      similarity_search_by_vector → 失败返回 []
      delete_by_metadata      → 默认失败返回 0；PGVector 实现覆盖为抛 RuntimeError
      get_by_id               → 失败返回 None
      get_by_metadata         → 失败返回 []
      count                   → 失败返回 0
      get_collection_info     → 失败返回 {"error": str}
      health_check            → 不可用返回 False
      close                   → 幂等不抛异常
    """

    def __init__(self, params: VectorStoreParams):
        self.params = params

    @abstractmethod
    def add_documents(self, nodes: list[TextNode], **kwargs) -> list[str]:
        """添加文档，失败抛 Exception"""
        ...

    @abstractmethod
    def similarity_search(
        self,
        query: str,
        k: int = 4,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        """文本相似度检索（需内置 embedding），默认返回空列表"""
        return []

    @abstractmethod
    def similarity_search_by_vector(
        self,
        query_vector: list[float],
        k: int = 4,
        metadata_filter: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[TextNode]:
        """向量相似度检索，失败返回 []"""
        ...

    @abstractmethod
    def delete(self, node_ids: list[str], **kwargs) -> bool:
        """删除文档，失败返回 False"""
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
    def get_by_id(self, node_id: str, **kwargs) -> TextNode | None:
        """根据 ID 获取文档，失败返回 None"""
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
    def count(self, **kwargs) -> int:
        """获取文档总数，失败返回 0"""
        ...

    @abstractmethod
    def clear(self, **kwargs) -> bool:
        """清空所有文档，失败返回 False"""
        ...

    @abstractmethod
    def get_collection_info(self) -> dict[str, Any]:
        """获取集合信息"""
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭连接/释放资源，幂等"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """健康检查"""
        ...
