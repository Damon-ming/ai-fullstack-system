# app-server/src/com/damon/ming/app/thread_pools.py
"""应用层通用线程池提交工具及少数共享池入口。"""

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from src.com.damon.ming.thread import ThreadPoolGroup, ThreadPoolManager


def get_rag_pool_group() -> ThreadPoolGroup:
    """获取 RAG 专用资源组，供 RAG 模块按预算创建线程池。"""
    return ThreadPoolManager().for_group("rag")


def create_database_pool() -> ThreadPoolExecutor:
    """创建统一的数据库线程池，使用 database 资源组的全部预算。"""
    manager = ThreadPoolManager()
    return manager.create_pool(
        "database", "default", manager.get_group_limit("database")
    )


def get_database_pool() -> ThreadPoolExecutor:
    """获取启动阶段创建的统一数据库线程池。"""
    return ThreadPoolManager().get_pool("database", "default")


def create_io_pool() -> ThreadPoolExecutor:
    """创建全局共享的通用 I/O 线程池。"""
    manager = ThreadPoolManager()
    return manager.create_pool("io", "default", manager.get_group_limit("io"))


def get_io_pool() -> ThreadPoolExecutor:
    """获取启动阶段创建的全局 I/O 线程池。"""
    return ThreadPoolManager().get_pool("io", "default")


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
