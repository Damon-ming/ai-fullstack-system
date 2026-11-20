"""聊天 SSE 事件名称。"""

from enum import StrEnum


class SseEventType(StrEnum):
    START = "start"
    DELTA = "delta"
    REASONING = "reasoning"
    DONE = "done"
    ERROR = "error"
