"""应用层线程池访问入口。

池名只在此模块映射，调用方通过用途明确的无参函数获取线程池。
"""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from src.com.damon.ming.thread import ThreadPoolManager


@dataclass(frozen=True)
class RagThreadPools:
    retrieval: ThreadPoolExecutor
    document: ThreadPoolExecutor
    inference: ThreadPoolExecutor
    rerank: ThreadPoolExecutor
    bm25: ThreadPoolExecutor


def get_rag_thread_pools() -> RagThreadPools:
    manager = ThreadPoolManager()
    return RagThreadPools(
        retrieval=manager.get_pool("retrieval"),
        document=manager.get_pool("document"),
        inference=manager.get_pool("inference"),
        rerank=manager.get_pool("rerank"),
        bm25=manager.get_pool("bm25"),
    )


def get_database_query_pool() -> ThreadPoolExecutor:
    return ThreadPoolManager().get_pool("database_query")


def get_document_pool() -> ThreadPoolExecutor:
    return ThreadPoolManager().get_pool("document")


async def run_in_pool(
    pool: ThreadPoolExecutor,
    func: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """在线程池中运行同步函数并等待结果，统一经过管理器指标统计。"""
    return await ThreadPoolManager().run(pool, func, *args, **kwargs)


def submit_to_pool(
    pool: ThreadPoolExecutor,
    func: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> Future:
    """向线程池提交后台任务，统一经过管理器指标统计。"""
    return ThreadPoolManager().submit(pool, func, *args, **kwargs)
