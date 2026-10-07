from src.com.damon.ming.ai.schemas.request import BaseLLMRequest


class ChatRequest(BaseLLMRequest):
    query: str
    think: bool
