# app-server/src/com/damon/ming/middleware/encryption/sse.py
"""SSE 字节流加密 —— 只加密 data: 字段，event / id / retry 保持明文。

为什么在中间件里做：
  SSE 响应不经过前端 axios 拦截器（浏览器原生 EventSource 没有响应
  拦截器），sse-transport 只能拿到原始字节。把加密放到中间件，SSE 与
  其它响应走同一套加密链路，chat_router 不再感知加解密。

实现要点（中间件看到的是 ASGI 字节流，必须自己做线格式解析）：
  - 按 `\n` 增量切行，chunk 边界可能落在行中间 → 先缓冲再切
  - 空行（`\n` 或 `\r\n`）表示一个事件结束
  - 多行 `data:` 先按 `\n` 拼接再加密（与客户端 SseParser 的语义一致），
    输出合并为单行 `data:`
  - 行终止符（`\n` / `\r\n`）按原样保留，不改变客户端看到的换行
  - 没有 data 字段的事件（心跳注释、只有 event/id 的事件）原样转发
  - 单个事件超出缓冲上限 → 抛 EncryptionError（fail-closed，不返回明文）
"""

from collections.abc import AsyncIterable, AsyncIterator

from src.com.damon.ming.app.encryption.key_material import DecryptedSessionKey
from src.com.damon.ming.encryption.v1.crypto_engine import AesGcmEngine
from src.com.damon.ming.exception import EncryptionError
from src.com.damon.ming.exception.error_codes import ErrorCode
from starlette.responses import Response, StreamingResponse

# 单个 SSE 事件的缓冲上限（1 MiB）：正常事件只有几十字节，
# 上限仅用于防止畸形流把内存吃光。
MAX_EVENT_BYTES = 1 << 20

_DATA_PREFIX = b"data:"
_CARRIAGE_RETURN = b"\r"


class _EventBuffer:
    """累积一个 SSE 事件的所有行，渲染时加密 data 字段。"""

    def __init__(self) -> None:
        self._lines: list[tuple[bytes, bytes]] = []  # (行内容, 行终止符)
        self._data: list[bytes] = []
        self.size = 0

    @property
    def has_data(self) -> bool:
        return bool(self._data)

    def add_line(self, line: bytes, terminator: bytes) -> None:
        """追加一行（line 不含行终止符，terminator 为 b"\\n" 或 b"\\r\\n"）。"""
        self.size += len(line) + len(terminator)
        if line.startswith(_DATA_PREFIX):
            # 与客户端 SseParser 对齐：data 值取 ":" 之后并去掉前导空白
            self._data.append(line[len(_DATA_PREFIX) :].lstrip())
        self._lines.append((line, terminator))

    def reset(self) -> None:
        self._lines.clear()
        self._data.clear()
        self.size = 0

    def render(self, session: DecryptedSessionKey) -> bytes:
        """渲染事件：data 行合并为一行密文，其余行原样保留。"""
        if not self._data:
            return b"".join(line + t for line, t in self._lines)

        payload = AesGcmEngine.encrypt_json(
            b"\n".join(self._data).decode("utf-8"),
            session.aes_key,
            session.key_id,
        )
        encrypted = payload.to_json().encode("utf-8")

        out = bytearray()
        data_written = False
        for line, terminator in self._lines:
            if line.startswith(_DATA_PREFIX):
                if data_written:
                    continue  # 多行 data 已合并成一行
                out += _DATA_PREFIX + b" " + encrypted + terminator
                data_written = True
            else:
                out += line + terminator
        return bytes(out)


async def encrypt_sse_stream(
    source: AsyncIterable[bytes],
    session: DecryptedSessionKey,
    max_event_bytes: int = MAX_EVENT_BYTES,
) -> AsyncIterator[bytes]:
    """逐事件加密 SSE 字节流（见模块 docstring 的线格式约定）。"""
    buffer = b""
    event = _EventBuffer()

    async for chunk in source:
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            terminator = b"\n"
            if line.endswith(_CARRIAGE_RETURN):
                line = line[: -len(_CARRIAGE_RETURN)]
                terminator = b"\r\n"

            if line == b"":
                # 空行 = 事件结束（事件本身 + 空行的终止符一起写回）
                yield event.render(session) + terminator
                event.reset()
                continue

            event.add_line(line, terminator)
            if event.size > max_event_bytes:
                raise EncryptionError(
                    f"SSE 事件超出缓冲上限（{max_event_bytes} 字节）",
                    biz_code=ErrorCode.ENCRYPT.ENCRYPTION_RESPONSE_FAILED,
                )

    # 末尾没有换行的残余行（畸形流兜底）
    if buffer:
        event.add_line(buffer, b"")
    if event.size:
        yield event.render(session)


def encrypt_sse_response(response: Response, session: DecryptedSessionKey) -> Response:
    """把 SSE 响应的字节流替换为逐事件加密后的流。

    只替换 body_iterator，其余头（content-type / cache-control /
    connection / x-accel-buffering）原样透传；content-length 丢弃
    （流长度已变，且流式响应本就不该带）。
    """
    headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() != "content-length"
    }
    return StreamingResponse(
        encrypt_sse_stream(response.body_iterator, session),
        status_code=response.status_code,
        headers=headers,
    )
