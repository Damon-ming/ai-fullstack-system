# app-server/src/com/damon/ming/middleware/encryption/chain.py
"""链式 gate 管道。

语义（每个 gate 必须遵守）：
  - handle(ctx, next_gate) 必须返回一个 Response
  - 「本层拦截」→ 直接 return 一个 Response（错误响应，或
    ctx.call_downstream() 拿到的下游响应），链上后续 gate 不再执行
  - 「本层放行」→ return await next_gate()

链的最后一环是 ResponseEncryptGate，它调用 next_gate() 即到达终端
（直接调用下游应用）。

新增处理步骤 = 新增一个 EncryptionGate 子类 +
build_encryption_chain() 里加一行，不改动其它 gate。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence

from fastapi import Request
from src.com.damon.ming.middleware.encryption.context import (
    CallNext,
    EncryptionContext,
)
from starlette.responses import Response

# next_gate 是「链上剩余部分」的句柄：调用它 = 交给下一环
GateCall = Callable[[], Awaitable[Response]]


class EncryptionGate(ABC):
    """链上一环的抽象。"""

    @abstractmethod
    async def handle(self, ctx: EncryptionContext, next_gate: GateCall) -> Response:
        """处理本层职责并返回响应。

        实现约定：
          - 本层拦截（拒绝 / 明文放行）→ 直接 return Response
          - 需要后续层处理            → return await next_gate()
        """
        raise NotImplementedError


class EncryptionChain:
    """gate 管道：顺序执行，命中即停。"""

    def __init__(self, gates: Sequence[EncryptionGate]) -> None:
        self._gates = tuple(gates)

    async def run(self, request: Request, call_next: CallNext) -> Response:
        """完整链：inbound → 下游 → outbound。"""
        ctx = EncryptionContext(request=request, downstream=call_next)
        return await self._advance(0, ctx)

    async def _advance(self, index: int, ctx: EncryptionContext) -> Response:
        if index >= len(self._gates):
            return await ctx.call_downstream()
        gate = self._gates[index]
        return await gate.handle(ctx, lambda: self._advance(index + 1, ctx))
