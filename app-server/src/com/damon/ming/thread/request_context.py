# app-server/src/com/damon/ming/thread/request_context.py
"""
请求级上下文 —— 封装 CancellationToken + 生命周期管理。

用法（在路由处理入口）：
    ctx = pool_mgr.create_request_context()
    try:
        # 将 ctx.cancellation_token 传给 AI 模块
        result = await ai_work(ctx.cancellation_token, ...)
    finally:
        ctx.cleanup()  # 标记取消 + 从注册表移除
"""

from __future__ import annotations

import time

from src.com.damon.ming.log import pin
from src.com.damon.ming.thread.cancellation import CancellationToken

logger = pin("thread.context")


class RequestContext:
    """请求级上下文 —— 封装 CancellationToken + 生命周期管理。

    生命周期：
      create → 绑定 token → 传给 AI 模块使用
             │ cleanup() → token.cancel() + token.dispose()
             │            → 从注册表移除，释放引用
    """

    def __init__(self, request_id: str, token: CancellationToken) -> None:
        self.request_id = request_id
        self.cancellation_token = token
        self.created_at = time.monotonic()

    def cleanup(self) -> None:
        """请求结束后的清理：取消 + 销毁令牌。

        幂等——多次调用无副作用（dispose 会从注册表移除，
        cancel 在已取消状态下是空操作）。
        """
        self.cancellation_token.cancel()
        self.cancellation_token.dispose()
        age = time.monotonic() - self.created_at
        logger.debug(
            "请求上下文已清理 | request_id=%s | lifetime=%.1fs",
            self.request_id,
            age,
        )
