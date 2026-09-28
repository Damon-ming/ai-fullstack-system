# app-server/src/com/damon/ming/ai/schemas/inference_params.py

# think=False 无思考过程
from pydantic import BaseModel, Field


class ChatRespNoThink(BaseModel):
    answer_content: str = Field(description="仅依据知识库作答，无相关内容填「不知道」，支持Markdown")

# think=True 带思考过程
class ChatRespWithThink(BaseModel):
    thinking_process: str = Field(description="分析问题、匹配知识库的推理过程")
    answer_content: str = Field(description="仅依据知识库作答，无相关内容填「不知道」，支持Markdown")
    
def get_chat_schema(think: bool):
    if think:
        return ChatRespWithThink.model_json_schema()
    return ChatRespNoThink.model_json_schema()