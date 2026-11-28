"""进程内 FIFO 后台任务队列，由定时器分批提交到专用线程池。"""

from __future__ import annotations

import inspect
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from src.com.damon.ming.app.thread_pools import submit_to_pool
from src.com.damon.ming.log import pin

logger = pin("app.background")


@dataclass(frozen=True)
class _QueuedTask:
    name: str
    callback: Callable[[], None]
    repeat: bool


class BackgroundTaskScheduler:
    """每轮从队首取一批任务；失败任务放回队尾等待下一轮。

    队列仅保存在本进程；需要跨重启重试的业务应另建持久化任务存储。
    """

    def __init__(
        self,
        default_executor: ThreadPoolExecutor,
        *,
        startup_delay_seconds: float,
        interval_seconds: float,
        batch_size: int,
    ) -> None:
        if (
            type(startup_delay_seconds) not in (int, float)
            or not math.isfinite(startup_delay_seconds)
            or startup_delay_seconds < 0
        ):
            raise ValueError("startup_delay_seconds 必须是非负有限数字")
        if (
            type(interval_seconds) not in (int, float)
            or not math.isfinite(interval_seconds)
            or interval_seconds <= 0
        ):
            raise ValueError("interval_seconds 必须是正有限数字")
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size 必须是正整数")

        self._executor = default_executor
        self._startup_delay_seconds = startup_delay_seconds
        self._interval_seconds = interval_seconds
        self._batch_size = batch_size
        self._condition = threading.Condition()
        self._queue: deque[_QueuedTask] = deque()
        self._periodic_names: set[str] = set()
        self._next_run_at: float | None = None
        self._thread: threading.Thread | None = None
        self._stopped = False

    def enqueue(self, name: str, callback: Callable[[], None]) -> None:
        """把一次性任务放入队尾；执行失败时自动重新排队。"""
        self._validate_task(name, callback)
        with self._condition:
            if self._stopped:
                raise RuntimeError("后台任务调度器已关闭")
            self._queue.append(_QueuedTask(name, callback, repeat=False))
            self._condition.notify_all()

    def register_periodic(self, name: str, callback: Callable[[], None]) -> None:
        """注册周期任务；每次执行结束后放回队尾。"""
        self._validate_task(name, callback)
        with self._condition:
            if self._stopped:
                raise RuntimeError("后台任务调度器已关闭")
            if name in self._periodic_names:
                raise ValueError(f"周期任务已注册: {name}")
            self._periodic_names.add(name)
            self._queue.append(_QueuedTask(name, callback, repeat=True))
            self._condition.notify_all()
        logger.info("周期任务已注册 | name=%s", name)

    def start(self) -> None:
        """启动调度线程；首次执行在启动延迟之后。"""
        with self._condition:
            if self._stopped:
                raise RuntimeError("后台任务调度器已关闭")
            if self._thread is not None:
                return
            self._next_run_at = time.monotonic() + self._startup_delay_seconds
            self._thread = threading.Thread(
                target=self._run,
                name="background-scheduler",
                daemon=True,
            )
            self._thread.start()
        logger.info("后台任务调度器已启动")

    def stop(self) -> None:
        """停止取任务；已提交的任务由线程池关闭流程等待。"""
        with self._condition:
            self._stopped = True
            self._condition.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()
        logger.info("后台任务调度器已停止")

    def _run(self) -> None:
        while True:
            with self._condition:
                if self._stopped:
                    return
                current = time.monotonic()
                assert self._next_run_at is not None
                if current < self._next_run_at:
                    self._condition.wait(timeout=self._next_run_at - current)
                    continue
                self._next_run_at = current + self._interval_seconds
                batch = [
                    self._queue.popleft()
                    for _ in range(min(self._batch_size, len(self._queue)))
                ]

            for task in batch:
                try:
                    with self._condition:
                        if self._stopped:
                            return
                        future = submit_to_pool(self._executor, self._execute, task)
                except Exception:
                    logger.exception("后台任务提交失败 | name=%s", task.name)
                    self._requeue(task)
                else:
                    future.add_done_callback(
                        lambda done, queued=task: self._on_done(queued, done)
                    )

    def _on_done(self, task: _QueuedTask, future: Future) -> None:
        failed = future.cancelled() or future.exception() is not None
        if failed or task.repeat:
            self._requeue(task)

    def _requeue(self, task: _QueuedTask) -> None:
        with self._condition:
            if not self._stopped:
                self._queue.append(task)
                self._condition.notify_all()

    @staticmethod
    def _execute(task: _QueuedTask) -> None:
        try:
            task.callback()
        except Exception:
            logger.exception("后台任务执行失败，下一轮重试 | name=%s", task.name)
            raise

    @staticmethod
    def _validate_task(name: str, callback: Callable[[], None]) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("后台任务名称不能为空")
        if not callable(callback) or inspect.iscoroutinefunction(callback):
            raise TypeError("后台任务必须是同步可调用对象")
