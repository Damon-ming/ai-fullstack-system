# app-server/src/com/damon/ming/chat/sse/emitter.py
"""
SSE 发射器 —— 管理事件 id 递增，返回 dict 供 EventSourceResponse 使用。

核心设计:
    - SseEvent 数据对象建模一条 SSE 事件（OOP，非字符串拼装）
    - SseEmitter.emit() 返回 dict，EventSourceResponse 自动序列化为 W3C 格式

主流程使用示例:
    emitter = SseEmitter(retry_ms=3000)

    yield emitter.emit("start", SseMessageFactory.start(data), retry=True)

    async for token in stream:
        yield emitter.emit("delta", SseMessageFactory.delta(ChatDeltaData(answer_content=token)))

    yield emitter.emit("done", SseMessageFactory.done())
"""

from dataclasses import dataclass

# ─── SSE 事件数据对象 ───────────────────────────────────────────────


@dataclass
class SseEvent:
    """一条 SSE 事件的数据对象 —— 先建模，EventSourceResponse 负责序列化"""

    event: str
    data: str
    id: str | None = None
    retry: int | None = None

    def to_dict(self) -> dict:
        """转为 dict，直接 yield 给 EventSourceResponse"""
        d: dict = {}
        if self.id is not None:
            d["id"] = self.id
        if self.event:
            d["event"] = self.event
        if self.retry is not None:
            d["retry"] = self.retry
        d["data"] = self.data
        return d


# ─── SSE 发射器 ─────────────────────────────────────────────────────


class SseEmitter:
    """SSE 事件发射器 —— emit() 返回 dict，适配 EventSourceResponse"""

    def __init__(self, retry_ms: int = 3000):
        self._event_seq = 0
        self._retry_ms = retry_ms

    # ─── 公共属性 ───────────────────────────────────────────────

    @property
    def last_event_id(self) -> str:
        """返回最后发出的事件 id（字符串），供日志 / Last-Event-ID 续传"""
        return str(self._event_seq)

    # ─── 核心 API ───────────────────────────────────────────────

    def create_event(
        self,
        event: str,
        data: str,
        *,
        retry: bool = False,
    ) -> SseEvent:
        """
        创建一条 SseEvent 对象。

        参数:
            event: 事件名 (start / delta / done / error)
            data:  已序列化的 JSON 字符串
            retry: 是否附加 retry: 字段（通常在 start 事件上设置）
        返回:
            SseEvent 数据对象
        """
        self._event_seq += 1
        return SseEvent(
            event=event,
            data=data,
            id=str(self._event_seq),
            retry=self._retry_ms if retry else None,
        )

    def emit(
        self,
        event: str,
        data: str,
        *,
        retry: bool = False,
    ) -> dict:
        """
        构造一条 SSE 事件 dict（便捷方法 = create_event + to_dict）。

        参数:
            event: 事件名 (start / delta / done / error)
            data:  已序列化的 JSON 字符串
            retry: 是否附加 retry: 字段
        返回:
            可直接 yield 给 EventSourceResponse 的 dict
        """
        return self.create_event(event, data, retry=retry).to_dict()
