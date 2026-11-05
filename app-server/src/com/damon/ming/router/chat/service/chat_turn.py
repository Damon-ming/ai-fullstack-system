# app-server/src/com/damon/ming/router/chat/service/chat_turn.py
"""
一轮对话的落库记录器 —— chat 链路专用。

chat_router 把本轮交付内容喂进来，结束时一次性落库：
  - 标题口径：用户问题前 40 字符（与历史列表展示一致）
  - 落库走 run_in_executor，同步 DB I/O 不阻塞事件循环
  - 异常吞掉返回 bool（落库失败不阻断主流程）
  - attempted 标记：调用方 finally 兜底只写一次

落库字段直接对应 history_turns 表，写入能力由 history 服务提供。
"""

import asyncio
from datetime import datetime

from src.com.damon.ming.ai.inference.base_inference import STREAM_TYPE_REASONING
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.history.service.history_service import HistoryService
from src.com.damon.ming.utils.time import now

logger = pin("chat.turn")

# 会话标题取用户问题前 N 字符（与历史列表展示口径一致）
TITLE_MAX_LEN = 40


class ChatTurnRecorder:
    """记录一轮对话的交付内容，结束时一次性落库。

    用法：
        recorder = _create_recorder(request, body)    # turn_id 自动生成
        recorder.record_token(token_type, text, at)   # 流式逐 token
        recorder.add_content(text)                    # 拦截文案 / 同步正文
        recorder.set_error(msg)                       # 失败轮次
        ok = await recorder.persist()
        if not recorder.attempted:                    # finally 兜底
            await recorder.persist()
    """

    def __init__(
        self,
        token: str,
        turn_id: str,
        conversation_id: str,
        query: str,
        query_at: datetime,
    ) -> None:
        self._token = token
        self._turn_id = turn_id
        self._conversation_id = conversation_id
        self._query = query
        self._query_at = query_at

        self._content_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._first_token_at: datetime | None = None
        self._reasoning_done_at: datetime | None = None
        self._answered_at: datetime | None = None
        self._error_msg: str | None = None

        self.attempted = False

    # ---- 内容累积 -------------------------------------------------------

    def add_content(self, text: str) -> None:
        """累积正文（拦截文案 / 同步回答）。"""
        if text:
            self._content_parts.append(text)

    def add_reasoning(self, text: str) -> None:
        """累积推理文本。"""
        if text:
            self._reasoning_parts.append(text)

    def record_token(self, token_type: str, text: str, at: datetime) -> None:
        """流式 token 入口：一次调用完成时刻标记 + 内容累积。"""
        if self._first_token_at is None:
            self._first_token_at = at
        if token_type == STREAM_TYPE_REASONING:
            self.add_reasoning(text)
            self._reasoning_done_at = at
        else:
            self.add_content(text)

    def mark_answered(self, at: datetime) -> None:
        """标记回答完成时刻。"""
        self._answered_at = at

    def set_error(self, msg: str | None) -> None:
        """设置用户可见的异常提示（成功 / 主动取消为 None）。"""
        self._error_msg = msg

    # ---- 内容读取 -------------------------------------------------------

    @property
    def content(self) -> str:
        """已累积的正文（同步链路缓冲拼接后回传客户端）。"""
        return "".join(self._content_parts)

    @property
    def reasoning(self) -> str:
        """已累积的推理文本（与流式链路同口径）。"""
        return "".join(self._reasoning_parts)

    # ---- 标识读取 -------------------------------------------------------

    @property
    def turn_id(self) -> str:
        """本轮 id（工厂自动生成，与 SSE start 事件下发的是同一个）。"""
        return self._turn_id

    @property
    def conversation_id(self) -> str:
        """所属会话 id（拦截轮次也要落库，需要会话归属）。"""
        return self._conversation_id

    # ---- 落库 -----------------------------------------------------------

    async def persist(self) -> bool:
        """把本轮已交付内容落库，返回是否写入成功。

        只尝试一次：重复调用直接返回 False，由调用方用 attempted
        判断是否需要 finally 兜底。

        DB 存的就是服务端实际交付给客户端的内容：正文 + 推理 + 异常提示，
        不含堆栈 / 错误码 / 日志。
        turn_id 由工厂自动生成，与 SSE start 事件下发的 turnId 一致，
        保证「客户端看到的」与「DB 里的」是同一轮。
        """
        if self.attempted:
            return False
        self.attempted = True
        try:
            return await asyncio.get_running_loop().run_in_executor(
                None, self._persist_sync
            )
        except Exception:
            logger.exception("轮次落库异常 | conversation_id=%s", self._conversation_id)
            return False

    def _persist_sync(self) -> bool:
        """同步落库（在线程池中执行）。"""
        return bool(
            HistoryService.save_turn(
                token=self._token,
                turn_id=self._turn_id,
                conversation_id=self._conversation_id,
                title=self._query[:TITLE_MAX_LEN],
                query=self._query,
                reasoning="".join(self._reasoning_parts),
                content="".join(self._content_parts),
                query_at=self._query_at,
                first_token_at=self._first_token_at,
                reasoning_done_at=self._reasoning_done_at,
                answered_at=self._answered_at or now(),
                error_msg=self._error_msg,
            )
        )
