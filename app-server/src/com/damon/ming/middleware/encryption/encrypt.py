# app-server/src/com/damon/ming/middleware/encryption/encrypt.py
"""响应加密策略（outbound）—— 一种响应类型对应一个策略。

策略是平级的：由 ResponseEncryptGate 持有，按顺序取第一个 supports()
命中的；都不命中则原样返回（文件下载、健康检查等非 JSON / 非 SSE 响应）。
"""

import json
from abc import ABC, abstractmethod

from src.com.damon.ming.app.encryption.key_management import DecryptedSessionKey
from src.com.damon.ming.encryption.v1.crypto_engine import AesGcmEngine
from src.com.damon.ming.exception import EncryptionError
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.encryption.context import EncryptionContext
from src.com.damon.ming.middleware.encryption.sse import encrypt_sse_response
from src.com.damon.ming.middleware.encryption.wire import (
    is_event_stream_response,
    is_json_response,
)
from starlette.responses import JSONResponse, Response

logger = pin("middleware.encryption")


class EncryptStrategy(ABC):
    """响应加密策略：一种响应类型对应一个策略。

    supports() 依据响应的 content-type 判断；apply() 返回加密后的响应。
    """

    @abstractmethod
    def supports(self, response: Response) -> bool:
        """是否由本策略处理该响应。"""
        raise NotImplementedError

    @abstractmethod
    async def apply(
        self, ctx: EncryptionContext, response: Response, session: DecryptedSessionKey
    ) -> Response:
        """返回加密后的响应。失败时抛 EncryptionError（fail-closed，不降级明文）。"""
        raise NotImplementedError


class JsonEncryptStrategy(EncryptStrategy):
    """restful 分支（application/json）：整个响应体加密成一个信封。"""

    def supports(self, response: Response) -> bool:
        return is_json_response(response)

    async def apply(
        self, ctx: EncryptionContext, response: Response, session: DecryptedSessionKey
    ) -> Response:
        """加密 JSON 响应。

        加密是安全关键路径，失败时拒绝返回（抛异常→500），
        不降级返回明文，避免加密模式被静默绕过。
        """
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        try:
            body_json = json.loads(response_body)
        except Exception as e:
            raise EncryptionError(
                f"响应加密失败：响应体不是合法 JSON（{type(e).__name__}）",
                biz_code=ErrorCode.ENCRYPT.ENCRYPTION_RESPONSE_FAILED,
            ) from e

        try:
            encrypted_payload = AesGcmEngine.encrypt_json(
                json.dumps(body_json, ensure_ascii=False),
                session.aes_key,
                session.key_id,
            )
        except Exception as e:
            raise EncryptionError(
                f"响应加密失败：{type(e).__name__}",
                biz_code=ErrorCode.ENCRYPT.ENCRYPTION_RESPONSE_FAILED,
            ) from e

        logger.debug("响应加密 | path=%s | body_bytes=%d", ctx.path, len(response_body))
        return JSONResponse(content=encrypted_payload.to_dict())


class SseEncryptStrategy(EncryptStrategy):
    """SSE 分支（text/event-stream）：逐事件加密 data 字段。

    event / id / retry 保持明文，客户端 SSE 解析器才能正确路由事件。
    """

    def supports(self, response: Response) -> bool:
        return is_event_stream_response(response)

    async def apply(
        self, ctx: EncryptionContext, response: Response, session: DecryptedSessionKey
    ) -> Response:
        return encrypt_sse_response(response, session)
