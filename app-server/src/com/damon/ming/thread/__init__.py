# app-server/src/com/damon/ming/thread/__init__.py
"""
线程管理模块 —— 统一管理所有 AI 子系统的线程资源。

子模块：
  - cancellation: CancellationToken（协作式取消令牌）
  - request_context: RequestContext（请求级上下文）
  - pool_manager: ThreadPoolManager（进程级线程池管理器单例）

公开导出：
  - CancellationToken: 协作式取消令牌
  - RequestContext: 请求级上下文（绑定 CancellationToken）
  - ThreadPoolManager: 进程级线程池管理器

用法：
  from src.com.damon.ming.thread import (
      CancellationToken,
      RequestContext,
      ThreadPoolManager,
  )

  # 在 AppInitializer.startup() 中：
  pool_mgr = ThreadPoolManager()
  pool_mgr.startup()

  # AI 模块中获取线程池：
  executor = pool_mgr.get_pool("retrieval")

  # 在路由入口创建请求上下文：
  ctx = pool_mgr.create_request_context()
  try:
      result = await ai_work(ctx.cancellation_token, ...)
  finally:
      ctx.cleanup()

  # 在 AppInitializer.shutdown() 中：
  pool_mgr.shutdown()
"""

from src.com.damon.ming.thread.cancellation import CancellationToken
from src.com.damon.ming.thread.pool_manager import ThreadPoolManager
from src.com.damon.ming.thread.request_context import RequestContext

__all__ = [
    "CancellationToken",
    "RequestContext",
    "ThreadPoolManager",
]
