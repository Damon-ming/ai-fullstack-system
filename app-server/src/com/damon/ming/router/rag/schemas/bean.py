from pydantic import Field
from src.com.damon.ming.ai.schemas.request import BaseLLMRequest


class ChatRequest(BaseLLMRequest):
    query: str
    reason: bool
    conversationId: str | None = Field(
        default=None,
        max_length=64,
        description="会话 id；为空则新建会话，非空则追加到该会话",
    )
