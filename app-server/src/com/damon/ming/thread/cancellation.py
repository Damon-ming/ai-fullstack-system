# app-server/src/com/damon/ming/thread/cancellation.py
"""
协作式取消机制 —— 通知线程"请尽快停止"。

AI 模块的循环体中应定期检查 is_cancelled()，主动退出。
不强制杀死线程（避免数据损坏），而是让线程体优雅返回。

提供：
  - CancellationToken: 取消令牌（create → check → cancel → dispose）
  - CancelResult: 取消结果（精确到哪一步取消的）
  - _TokenRegistry: 进程级注册表，支持按 request_id 批量取消
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field

from src.com.damon.ming.log import pin

logger = pin("thread.cancellation")


@dataclass
class CancelResult:
    """取消结果 —— 精确记录取消发生的位置和上下文。

    用法：
        result = CancelResult(step="rag_retrieval")
        result.mark_completed("query_parse")
        result.mark_completed("vector_search")
        # → result.step == "rag_retrieval"
        # → result.completed_steps == ["query_parse", "vector_search"]
    """

    step: str = ""                        # 取消发生的步骤名
    completed_steps: list[str] = field(default_factory=list)  # 已完成的步骤
    cancelled_at: float = field(default_factory=time.monotonic)

    def mark_completed(self, step_name: str) -> None:
        """标记某步骤已完成"""
        self.completed_steps.append(step_name)

    def was_cancelled(self) -> bool:
        """是否已发生取消"""
        return bool(self.step)

    def describe(self) -> str:
        """人类可读的取消描述"""
        if not self.step:
            return "未取消"
        done = ", ".join(self.completed_steps) if self.completed_steps else "无"
        return f"取消于 [{self.step}] | 已完成: [{done}]"


class CancellationToken:
    """协作式取消令牌。

    生命周期：
      create → is_cancelled()=False
              │ cancel() → is_cancelled()=True
              │          线程体检测后退出
              │          注册的 asyncio Task 立即取消
              │          token.dispose() → 管理器移除

    用法（异步场景）：
      token = CancellationToken(...)
      token.register_task(asyncio.current_task())
      # 当 cancel() 被调用时，current_task() 会立即在 await 点抛出 CancelledError
    """

    def __init__(self, token_id: str, registry: _TokenRegistry) -> None:
        self._token_id = token_id
        self._registry = registry
        self._cancelled = threading.Event()
        self._created_at = time.monotonic()
        self._task: object | None = None
        self._task_lock = threading.Lock()

    @property
    def token_id(self) -> str:
        return self._token_id

    def is_cancelled(self) -> bool:
        """线程体在循环中调用此方法检查是否应退出。"""
        return self._cancelled.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """阻塞等待取消信号。返回 True 表示已取消。"""
        return self._cancelled.wait(timeout)

    def register_task(self, task: object) -> None:
        """注册一个 asyncio.Task，cancel() 时自动取消该 task。

        应在协程开始处调用：token.register_task(asyncio.current_task())
        若 cancel() 先于注册到达，注册后立即取消 task。
        """
        with self._task_lock:
            self._task = task
            if self._cancelled.is_set() and hasattr(task, "cancel"):
                task.cancel()
                logger.info(
                    "取消令牌(已触发)注册新任务时立即取消 | token_id=%s",
                    self._token_id,
                )

    def cancel(self) -> None:
        """发送取消信号。幂等——多次调用无副作用。

        同时取消已注册的 asyncio Task（如有），使当前 await 点立即中断。
        """
        self._cancelled.set()
        with self._task_lock:
            task = self._task
        if task is not None and hasattr(task, "cancel"):
            task.cancel()
            logger.info(
                "取消令牌已触发(联动 Task 取消) | token_id=%s | age=%.1fs",
                self._token_id,
                time.monotonic() - self._created_at,
            )
        else:
            logger.info(
                "取消令牌已触发 | token_id=%s | age=%.1fs",
                self._token_id,
                time.monotonic() - self._created_at,
            )

    def dispose(self) -> None:
        """请求结束后的清理：从注册表移除，释放引用。"""
        self._registry.remove(self._token_id)
        age = time.monotonic() - self._created_at
        logger.debug(
            "取消令牌已销毁 | token_id=%s | lifetime=%.1fs", self._token_id, age
        )


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
