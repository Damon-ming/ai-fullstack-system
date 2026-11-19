# app-server/src/com/damon/ming/thread/pool_manager.py
"""
线程池管理器 —— 统一管理资源组预算和线程池生命周期。

架构：
  ┌──────────────────────────────────────────────────────────┐
  │                ThreadPoolManager (进程单例)                │
  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
  │  │ "retrieval"  │  │ "document"   │  │ "inference"    │  … │
  │  │  pool(4)     │  │  pool(8)     │  │  pool(2)       │  │
  │  └─────────────┘  └──────────────┘  └────────────────┘  │
  └──────────────────────────────────────────────────────────┘

职责：
  - 统一校验资源组和进程级 worker 预算
  - 组件按需创建命名池，管理器统一统计和关闭
  - 请求级作用域：通过 create_request_scope() 创建
  - 优雅关闭：shutdown 时先取消所有令牌，再关闭所有线程池

用法：
  # 在 AppInitializer 中：
  pool_mgr = ThreadPoolManager()
  pool_mgr.startup(group_limits={"rag": 17, "database": 3}, max_total_workers=20)

  # AI 模块获取命名线程池：
  executor = pool_mgr.create_pool("rag", "retrieval", max_workers=4)

  # 请求级作用域（在路由入口处）：
  scope = pool_mgr.create_request_scope()
  try:
      future = executor.submit(work_fn, scope.cancellation_token, ...)
  finally:
      scope.cleanup()

  # AppInitializer.shutdown 中：
  pool_mgr.shutdown()
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Self

from src.com.damon.ming.log import pin
from src.com.damon.ming.thread.cancellation import CancellationToken
from src.com.damon.ming.thread.request_scope import RequestScope
from src.com.damon.ming.utils.uuid import generate_uuid_hex

logger = pin("thread.pool_manager")


class ThreadPoolManager:
    """进程级线程池管理器 —— 统一管理所有 AI 子系统线程资源。

    app/config/thread 配置全局资源组预算；组内池容量由所属模块配置。
    管理器统一校验预算、统计状态并关闭所有池。

    使用方式：
        # AppInitializer.startup 中：
        self.pool_mgr = ThreadPoolManager()
        self.pool_mgr.startup(
            group_limits={"rag": 17, "database": 3}, max_total_workers=20
        )

        # AI 模块中获取线程池：
        executor = self.pool_mgr.create_pool("rag", "retrieval", max_workers=4)
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

    def startup(self, group_limits: dict[str, int], max_total_workers: int) -> None:
        """初始化线程资源预算；各组件在此后按预算创建命名池。

        Args:
            group_limits: 各资源组 worker 上限，如 {"rag": 17, "database": 3}。
            max_total_workers: 进程级 worker 总上限。
        """
        with self._instance_lock:
            if self._initialized:
                logger.warning("ThreadPoolManager 已初始化，跳过重复 startup")
                return

            if any(
                type(limit) is not int or limit <= 0 for limit in group_limits.values()
            ):
                raise ValueError("线程资源组上限必须是正整数")
            if type(max_total_workers) is not int or max_total_workers <= 0:
                raise ValueError("全局线程上限必须是正整数")
            if sum(group_limits.values()) > max_total_workers:
                raise ValueError("线程资源组预算总和超过全局线程上限")

            self._group_limits = dict(group_limits)
            self._max_total_workers = max_total_workers
            self._pool_configs: dict[str, int] = {}
            self._pools: dict[str, ThreadPoolExecutor] = {}
            self._pool_metrics: dict[str, dict[str, int]] = {}
            self._metrics_lock = threading.Lock()

            self._initialized = True
            logger.info(
                "ThreadPoolManager 初始化完成 | group_limits=%s | max_total=%d",
                self._group_limits,
                max_total_workers,
            )

    def shutdown(self, wait: bool = True, cancel_futures: bool = True) -> None:
        """关闭所有线程池。

        Args:
            wait: 是否等待已提交任务完成。shutdown 时应 True。
            cancel_futures: 是否取消未开始的任务。
        """
        if not self._initialized:
            return

        # 1. 关闭所有线程池（RequestScope.cleanup() 会在路由层单独取消各令牌）
        for name, pool in self._pools.items():
            try:
                pool.shutdown(wait=wait, cancel_futures=cancel_futures)
                logger.info("线程池已关闭 | name=%s", name)
            except Exception as e:
                logger.warning("线程池关闭异常 | name=%s | error=%s", name, e)

        self._pools.clear()
        self._pool_configs.clear()
        self._pool_metrics.clear()
        self._group_limits.clear()
        self._initialized = False

        # 释放单例引用（便于测试重置）
        ThreadPoolManager._instance = None
        logger.info("ThreadPoolManager 已关闭")

    def get_group_limit(self, group: str) -> int:
        """获取资源组的 worker 总预算，供所属模块分配内部线程池。"""
        if not self._initialized:
            raise RuntimeError("ThreadPoolManager 未初始化，请先调用 startup()")
        if group not in self._group_limits:
            raise ValueError(f"未知线程资源组: {group}")
        return self._group_limits[group]

    def for_group(self, group: str) -> ThreadPoolGroup:
        """创建仅能访问指定资源组的线程池能力接口。"""
        self.get_group_limit(group)
        return ThreadPoolGroup(self, group)

    def create_pool(
        self, group: str, name: str, max_workers: int
    ) -> ThreadPoolExecutor:
        """由资源组内部按需创建命名线程池；重复申请须容量一致。"""
        return self._create_pool(group, name, max_workers)

    def _create_pool(
        self, group: str, name: str, max_workers: int
    ) -> ThreadPoolExecutor:
        if not self._initialized:
            raise RuntimeError("ThreadPoolManager 未初始化，请先调用 startup()")
        if group not in self._group_limits:
            raise ValueError(f"未知线程资源组: {group}")
        if not name or type(max_workers) is not int or max_workers <= 0:
            raise ValueError("线程池名称必须非空，max_workers 必须是正整数")

        pool_key = f"{group}:{name}"
        existing = self._pools.get(pool_key)
        if existing is not None:
            if self._pool_configs[pool_key] != max_workers:
                raise ValueError(
                    f"线程池 {pool_key} 已以 max_workers="
                    f"{self._pool_configs[pool_key]} 创建，不能改为 {max_workers}"
                )
            return existing

        group_total = sum(
            workers
            for key, workers in self._pool_configs.items()
            if key.startswith(f"{group}:")
        )
        if group_total + max_workers > self._group_limits[group]:
            raise ValueError(
                f"线程组 {group} 预算超限: "
                f"{group_total + max_workers}>{self._group_limits[group]}"
            )
        total = sum(self._pool_configs.values()) + max_workers
        if total > self._max_total_workers:
            raise ValueError(f"全局线程预算超限: {total}>{self._max_total_workers}")

        pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=pool_key)
        self._pool_configs[pool_key] = max_workers
        self._pools[pool_key] = pool
        self._pool_metrics[pool_key] = {
            "submitted": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        logger.info("线程池已创建 | name=%s | max_workers=%d", pool_key, max_workers)
        return pool

    def get_pool(self, group: str, name: str) -> ThreadPoolExecutor:
        """获取资源组内已注册的命名线程池。

        Args:
            group: 资源组，如 "rag" 或 "database"。
            name: 线程池名称，如 "retrieval"、"document"。

        Returns:
            ThreadPoolExecutor 实例。

        Raises:
            RuntimeError: 管理器未初始化。
            ValueError: 线程池尚未由所属组件创建。
        """
        if not self._initialized:
            raise RuntimeError("ThreadPoolManager 未初始化，请先调用 startup()")

        pool_key = f"{group}:{name}"
        pool = self._pools.get(pool_key)
        if pool is not None:
            return pool

        raise ValueError(
            f"线程池 '{pool_key}' 尚未创建。已注册: {list(self._pools.keys())}"
        )

    def submit(self, pool: ThreadPoolExecutor, func, /, *args, **kwargs) -> Future:
        """统一提交同步任务并跟踪池级任务指标。"""
        pool_name = next(
            (name for name, registered in self._pools.items() if registered is pool),
            None,
        )
        if pool_name is None:
            raise ValueError("只能向 ThreadPoolManager 管理的线程池提交任务")

        def invoke():
            with self._metrics_lock:
                self._pool_metrics[pool_name]["running"] += 1
            try:
                return func(*args, **kwargs)
            finally:
                with self._metrics_lock:
                    self._pool_metrics[pool_name]["running"] -= 1

        with self._metrics_lock:
            self._pool_metrics[pool_name]["submitted"] += 1
        try:
            future = pool.submit(invoke)
        except Exception:
            with self._metrics_lock:
                self._pool_metrics[pool_name]["submitted"] -= 1
            raise

        def record_completion(done: Future) -> None:
            with self._metrics_lock:
                if done.cancelled():
                    self._pool_metrics[pool_name]["cancelled"] += 1
                elif done.exception() is not None:
                    self._pool_metrics[pool_name]["failed"] += 1
                else:
                    self._pool_metrics[pool_name]["completed"] += 1

        future.add_done_callback(record_completion)
        return future

    async def run(self, pool: ThreadPoolExecutor, func, /, *args, **kwargs) -> Any:
        """提交同步任务并异步等待结果。"""
        import asyncio

        return await asyncio.wrap_future(self.submit(pool, func, *args, **kwargs))

    def create_request_scope(self, request_id: str | None = None) -> RequestScope:
        """创建请求级作用域，绑定一个 CancellationToken。

        Args:
            request_id: 请求标识（默认自动生成 UUID）。

        Returns:
            RequestScope 实例。
        """
        req_id = request_id or f"req-{generate_uuid_hex()[:12]}"
        cancellation_token = CancellationToken(token_id=f"{req_id}-tok")
        scope = RequestScope(request_id=req_id, cancellation_token=cancellation_token)
        logger.debug("请求作用域已创建 | request_id=%s", req_id)
        return scope

    def get_stats(self) -> dict[str, Any]:
        """获取线程池运行状态，用于监控。"""
        stats: dict[str, Any] = {
            "initialized": self._initialized,
            "max_total_workers": self._max_total_workers,
            "group_limits": self._group_limits,
            "pools": {},
        }
        for name, pool in self._pools.items():
            stats["pools"][name] = {
                "max_workers": pool._max_workers,
                "worker_threads": len(pool._threads)
                if hasattr(pool, "_threads")
                else "n/a",
                **self._pool_metrics[name],
            }
        return stats


class ThreadPoolGroup:
    """限定在单个资源组内创建和获取线程池的接口。"""

    def __init__(self, manager: ThreadPoolManager, group: str) -> None:
        self._manager = manager
        self._group = group

    def create_pool(self, name: str, max_workers: int) -> ThreadPoolExecutor:
        """在授权的资源组内创建或获取命名线程池。"""
        return self._manager.create_pool(self._group, name, max_workers)

    def get_pool(self, name: str) -> ThreadPoolExecutor:
        """获取授权资源组中已创建的命名线程池。"""
        return self._manager.get_pool(self._group, name)
