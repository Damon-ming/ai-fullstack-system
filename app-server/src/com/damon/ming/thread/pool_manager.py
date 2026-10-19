# app-server/src/com/damon/ming/thread/pool_manager.py
"""
线程池管理器 —— 统一管理所有 AI 子系统线程资源。

架构：
  ┌──────────────────────────────────────────────────────────┐
  │                ThreadPoolManager (进程单例)                │
  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
  │  │ "retrieval"  │  │ "document"   │  │ "inference"    │  … │
  │  │  pool(4)     │  │  pool(8)     │  │  pool(2)       │  │
  │  └─────────────┘  └──────────────┘  └────────────────┘  │
  └──────────────────────────────────────────────────────────┘

职责：
  - 集中式命名线程池：按需创建，全局复用，避免每个模块各自创建/销毁
  - 请求级上下文：通过 create_request_context() 创建
  - 优雅关闭：shutdown 时先取消所有令牌，再关闭所有线程池

用法：
  # 在 AppInitializer 中：
  pool_mgr = ThreadPoolManager()
  pool_mgr.startup(pool_configs={"retrieval": 4, "document": 8, ...})

  # AI 模块获取命名线程池：
  executor = pool_mgr.get_pool("retrieval")

  # 请求级上下文（在路由入口处）：
  ctx = pool_mgr.create_request_context()
  try:
      future = executor.submit(work_fn, ctx.cancellation_token, ...)
  finally:
      ctx.cleanup()

  # AppInitializer.shutdown 中：
  pool_mgr.shutdown()
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Self

from src.com.damon.ming.log import pin
from src.com.damon.ming.thread.cancellation import CancellationToken
from src.com.damon.ming.thread.request_context import RequestContext

logger = pin("thread.pool_manager")


class ThreadPoolManager:
    """进程级线程池管理器 —— 统一管理所有 AI 子系统线程资源。

    所有线程池配置由 YAML 文件驱动（thread-config.yaml），
    启动时固化，运行期通过 get_pool(name) 获取。

    使用方式：
        # AppInitializer.startup 中：
        self.pool_mgr = ThreadPoolManager()
        self.pool_mgr.startup(pool_configs={"retrieval": 4, "document": 8, ...})

        # AI 模块中获取线程池：
        executor = self.pool_mgr.get_pool("retrieval")
        future = executor.submit(work, cancellation_token, ...)

        # AppInitializer.shutdown 中：
        self.pool_mgr.shutdown()
    """

    _instance: ThreadPoolManager | None = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> Self:
        """进程单例 —— 所有模块共享同一个管理器。"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def startup(self, pool_configs: dict[str, int]) -> None:
        """初始化所有命名线程池。

        Args:
            pool_configs: 线程池配置，格式：{"pool_name": max_workers, ...}
                         由 ThreadPoolConfigLoader 从 YAML 加载后传入。
        """
        with self._instance_lock:
            if self._initialized:
                logger.warning("ThreadPoolManager 已初始化，跳过重复 startup")
                return

            self._pool_configs = dict(pool_configs)
            self._pools: dict[str, ThreadPoolExecutor] = {}

            for name, max_workers in self._pool_configs.items():
                self._pools[name] = ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix=f"AI-{name}",
                )
                logger.info(
                    "线程池已创建 | name=%s | max_workers=%d", name, max_workers
                )

            self._initialized = True
            logger.info("ThreadPoolManager 初始化完成 | pools=%d", len(self._pools))

    def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
        """关闭所有线程池。

        Args:
            wait: 是否等待已提交任务完成。shutdown 时应 True。
            cancel_futures: 是否取消未开始的任务。
        """
        if not self._initialized:
            return

        # 1. 关闭所有线程池（RequestContext.cleanup() 会在路由层单独取消各令牌）
        for name, pool in self._pools.items():
            try:
                pool.shutdown(wait=wait, cancel_futures=cancel_futures)
                logger.info("线程池已关闭 | name=%s", name)
            except Exception as e:
                logger.warning("线程池关闭异常 | name=%s | error=%s", name, e)

        self._pools.clear()
        self._initialized = False

        # 释放单例引用（便于测试重置）
        ThreadPoolManager._instance = None
        logger.info("ThreadPoolManager 已关闭")

    def get_pool(self, name: str) -> ThreadPoolExecutor:
        """获取命名线程池。

        Args:
            name: 线程池名称（如 "retrieval", "document", "rerank"）。

        Returns:
            ThreadPoolExecutor 实例。

        Raises:
            RuntimeError: 管理器未初始化。
            ValueError: 线程池不存在（未在 YAML 中配置）。
        """
        if not self._initialized:
            raise RuntimeError("ThreadPoolManager 未初始化，请先调用 startup()")

        pool = self._pools.get(name)
        if pool is not None:
            return pool

        raise ValueError(f"线程池 '{name}' 不存在。已注册: {list(self._pools.keys())}")

    def create_request_context(self, request_id: str | None = None) -> RequestContext:
        """创建请求级上下文，绑定一个 CancellationToken。

        Args:
            request_id: 请求标识（默认自动生成 UUID）。

        Returns:
            RequestContext 实例。
        """
        req_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
        token = CancellationToken(token_id=f"{req_id}-tok")
        ctx = RequestContext(request_id=req_id, token=token)
        logger.debug("请求上下文已创建 | request_id=%s", req_id)
        return ctx

    def get_stats(self) -> dict[str, Any]:
        """获取线程池运行状态，用于监控。"""
        stats: dict[str, Any] = {
            "initialized": self._initialized,
            "pools": {},
        }
        for name, pool in self._pools.items():
            stats["pools"][name] = {
                "max_workers": pool._max_workers,
                "active_threads": len(pool._threads)
                if hasattr(pool, "_threads")
                else "n/a",
            }
        return stats

    @contextmanager
    def request_scope(self, request_id: str | None = None) -> Iterator[RequestContext]:
        """上下文管理器：自动创建 + cleanup 请求上下文。

        用法：
            async with pool_mgr.request_scope() as ctx:
                result = await ai_work(ctx.cancellation_token, ...)
        """
        ctx = self.create_request_context(request_id)
        try:
            yield ctx
        finally:
            ctx.cleanup()
