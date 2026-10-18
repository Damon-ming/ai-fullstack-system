# app-server/src/com/damon/ming/ai/schemas/inference_params.py

# reasoning=False 无推理过程
from pydantic import BaseModel, Field


class ChatRespNoReasoning(BaseModel):
    answer_content: str = Field(
        description="仅依据知识库作答，无相关内容填「不知道」，支持Markdown"
    )


# reasoning=True 带推理过程
class ChatRespWithReasoning(BaseModel):
    reasoning_process: str = Field(description="分析问题、匹配知识库的推理过程")
    answer_content: str = Field(
        description="仅依据知识库作答，无相关内容填「不知道」，支持Markdown"
    )


def get_chat_schema(reason: bool):
    if reason:
        return ChatRespWithReasoning.model_json_schema()
    return ChatRespNoReasoning.model_json_schema()
