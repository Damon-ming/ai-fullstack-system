# app-server/src/com/damon/ming/thread/request_scope.py
"""
请求级作用域 —— 封装 CancellationToken + 生命周期管理。

与 middleware/request_context.py 的 RequestContext 区分：那个的 token 是
认证令牌（字符串），本对象的 cancellation_token 是 CancellationToken。

用法（在路由处理入口）：
    ctx = pool_mgr.create_request_scope()
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

logger = pin("thread.request_scope")


class RequestScope:
    """请求级作用域 —— 封装 CancellationToken + 生命周期管理。

    生命周期：
      create → 绑定令牌 → 传给 AI 模块使用
             │ cleanup() → token.cancel() + token.dispose()
             │            → 从注册表移除，释放引用
    """

    def __init__(self, request_id: str, cancellation_token: CancellationToken) -> None:
        self.request_id = request_id
        self.cancellation_token = cancellation_token
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
            "请求作用域已清理 | request_id=%s | lifetime=%.1fs",
            self.request_id,
            age,
        )
