# app-server/src/com/damon/ming/router/chat/sse/encryption.py
"""
SSE 事件加密 —— 逐事件加密 data 字段（event / id / retry 保持明文）。

为什么由本模块做，而不是 EncryptionMiddleware：
  中间件拿到的是 ASGI 字节流，要只加密 `data:` 而保留 `event:` / `id:` /
  `retry:`，就得在中间件里重新实现一遍 SSE 线格式解析 —— 行缓冲、
  多行 data 用 `\n` 拼接、空行切分事件，以及最麻烦的 chunk 边界
  （一个 chunk 可能只包含半行）。本模块拿的是 SseEmitter 产出的结构化
  事件 dict，加密 data 是精确的、零解析的。

  代价：新增 SSE 端点时必须记得调用本函数（当前只有 chat 一个 SSE 端点）。

会话来源：
  EncryptionMiddleware 解密请求后写入 request.state.enc_session。
  无会话（debug 关闭加密 / 命中白名单）时原样返回生成器，保持明文兼容 ——
  release 下中间件已保证非白名单请求必然带会话，因此这里不会误放行。
"""

from fastapi import Request
from src.com.damon.ming.encryption.v1.crypto_engine import AesGcmEngine


def encrypt_sse_events(request: Request, generator):
    """按服务端开关逐事件加密 SSE 的 data 字段。

    参数：
      request:   当前请求（读取中间件写入的加密会话）
      generator: 产出事件 dict 的异步生成器

    返回：
      有加密会话 → 包一层逐事件加密的异步生成器
      无加密会话 → 原样返回传入的生成器（明文链路）
    """
    session = getattr(request.state, "enc_session", None)
    if session is None:
        return generator

    async def _encrypt_events():
        async for event in generator:
            data = event.get("data")
            if data:
                payload = AesGcmEngine.encrypt_json(
                    data, session.aes_key, session.key_id
                )
                event["data"] = payload.to_json()
            yield event

    return _encrypt_events()
