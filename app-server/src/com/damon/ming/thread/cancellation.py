# app-server/src/com/damon/ming/thread/cancellation.py
"""
协作式取消机制 —— 取消当前 asyncio 协程。

用法（异步场景）：
  token = CancellationToken(token_id, registry)
  token.register_task(asyncio.current_task())
  # 当 cancel() 被调用时，current_task() 在下一个 await 点抛出 CancelledError

注册表按 request_id 管理 token，支持批量取消：
  registry.cancel_request(request_id)  # 取消该请求关联的所有 token
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class CancellationToken:
    """请求级取消令牌 —— 取消当前 asyncio 协程。

    生命周期：
      create → 注册到 Registry
      use    → register_task(current_task)
      cancel → task.cancel() → CancelledError 在下一个 await 点传播
      dispose() → 从 Registry 移除
    """

    def __init__(self, token_id: str, registry: _TokenRegistry) -> None:
        self._token_id = token_id
        self._registry = registry
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
        """请求结束后从注册表移除。"""
        self._registry.remove(self._token_id)
        logger.debug("取消令牌已销毁 | token_id=%s", self._token_id)


class _TokenRegistry:
    """进程级取消令牌注册表 —— 支持按 request_id 批量取消。"""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._request_map: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.Lock()

    def register(self, request_id: str, token: CancellationToken) -> None:
        with self._lock:
            self._tokens[token.token_id] = token
            self._request_map[request_id].add(token.token_id)

    def remove(self, token_id: str) -> None:
        with self._lock:
            self._tokens.pop(token_id, None)
            for req_id, tokens in list(self._request_map.items()):
                tokens.discard(token_id)
                if not tokens:
                    del self._request_map[req_id]

    def cancel_request(self, request_id: str) -> None:
        """取消某 request 关联的所有令牌。"""
        with self._lock:
            token_ids = self._request_map.get(request_id, set()).copy()
        for tid in token_ids:
            token = self._tokens.get(tid)
            if token is not None:
                token.cancel()
        logger.info(
            "请求级取消完成 | request_id=%s | tokens=%d", request_id, len(token_ids)
        )

    def cancel_all(self) -> None:
        """取消所有令牌（app shutdown 时）。"""
        with self._lock:
            all_ids = list(self._tokens.keys())
        for tid in all_ids:
            token = self._tokens.get(tid)
            if token is not None:
                token.cancel()
        logger.info("全局取消完成 | tokens=%d", len(all_ids))

    def count(self) -> int:
        with self._lock:
            return len(self._tokens)
