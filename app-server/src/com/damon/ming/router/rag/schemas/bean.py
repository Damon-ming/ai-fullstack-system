from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str
    reason: bool
    conversationId: str | None = Field(
        default=None,
        max_length=64,
        description="会话 id；为空则新建会话，非空则追加到该会话",
    )
