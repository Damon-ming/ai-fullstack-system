# app-server/src/com/damon/ming/thread/__init__.py
"""
线程管理模块 —— 统一管理所有 AI 子系统的线程资源。

子模块：
  - pool_manager: ThreadPoolManager（进程级线程池管理器单例）

公开导出：
  - ThreadPoolManager: 进程级线程池管理器
  - ThreadPoolGroup: 限定到单个资源组的线程池接口

用法：
  from src.com.damon.ming.thread import ThreadPoolManager

  # 在 AppInitializer.startup() 中：
  pool_mgr = ThreadPoolManager()
  pool_mgr.startup(group_limits={"rag": 17, "database": 3}, max_total_workers=20)

  # AI 模块中获取线程池：
  executor = pool_mgr.create_pool("rag", "retrieval", max_workers=4)

  # 在 AppInitializer.shutdown() 中：
  pool_mgr.shutdown()
"""

from src.com.damon.ming.thread.pool_manager import ThreadPoolGroup, ThreadPoolManager

__all__ = [
    "ThreadPoolGroup",
    "ThreadPoolManager",
]
