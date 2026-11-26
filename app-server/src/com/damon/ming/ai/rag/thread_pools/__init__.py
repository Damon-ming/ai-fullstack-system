# app-server/src/com/damon/ming/ai/rag/thread_pools/__init__.py
"""RAG 内部线程池的初始化和访问入口。"""

from concurrent.futures import ThreadPoolExecutor

from src.com.damon.ming.ai.rag.thread_pools.config import RagThreadPoolConfig
from src.com.damon.ming.thread import ThreadPoolGroup


class RagThreadPools:
    """根据 AI 配置初始化 RAG 线程池，并按名称提供访问。"""

    def __init__(self) -> None:
        self._pools: dict[str, ThreadPoolExecutor] = {}

    def initialize(self, pools: ThreadPoolGroup, config: dict[str, object]) -> None:
        """在已授权的 RAG 资源组中创建配置的线程池。"""
        if self._pools:
            raise RuntimeError("RAG 线程池已经初始化")

        parsed_config = RagThreadPoolConfig.from_mapping(config)

        self._pools = {
            name: pools.create_pool(name, workers)
            for name, workers in parsed_config.workers.items()
        }

    def _get_pool(self, name: str) -> ThreadPoolExecutor:
        """获取已初始化的命名线程池。"""
        if not self._pools:
            raise RuntimeError("RAG 线程池尚未初始化")
        try:
            return self._pools[name]
        except KeyError as exc:
            raise ValueError(f"未知 RAG 线程池: {name}") from exc

    def get_retrieval_pool(self) -> ThreadPoolExecutor:
        return self._get_pool("retrieval")

    def get_document_pool(self) -> ThreadPoolExecutor:
        return self._get_pool("document")

    def get_rerank_pool(self) -> ThreadPoolExecutor:
        return self._get_pool("rerank")

    def get_bm25_pool(self) -> ThreadPoolExecutor:
        return self._get_pool("bm25")
