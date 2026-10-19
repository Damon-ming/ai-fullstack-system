# app-server/src/com/damon/ming/thread/cancellation.py
"""
协作式取消机制 —— 取消当前 asyncio 协程。

用法（异步场景）：
  token = CancellationToken(token_id)
  token.register_task(asyncio.current_task())
  # 当 cancel() 被调用时，current_task() 在下一个 await 点抛出 CancelledError
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CancellationToken:
    """请求级取消令牌 —— 取消当前 asyncio 协程。

    生命周期：
      create → register_task(current_task) → cancel() → CancelledError 在下一个 await 点传播
                                                              → dispose() 释放引用
    """

    def __init__(self, token_id: str) -> None:
        self._token_id = token_id
        self._task: object | None = None

    @property
    def token_id(self) -> str:
        return self._token_id

    def register_task(self, task: object) -> None:
        """注册当前协程的 Task，cancel() 时直接取消该 Task。"""
        self._task = task

    def cancel(self) -> None:
        """发送取消信号（幂等——多次调用无副作用）。"""
        if self._task is not None and hasattr(self._task, "cancel"):
            self._task.cancel()
            logger.info("取消令牌已触发 | token_id=%s", self._token_id)

    def dispose(self) -> None:
        """请求结束后释放引用。"""
        self._task = None
        logger.debug("取消令牌已销毁 | token_id=%s", self._token_id)
