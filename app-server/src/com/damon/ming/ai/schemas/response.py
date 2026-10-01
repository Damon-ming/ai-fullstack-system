# app-server/src/com/damon/ming/ai/schemas/response.py

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# 定义泛型，用于包裹具体的业务数据
T = TypeVar("T")
F = TypeVar("F")


# ================= 1. 响应外壳 =================
class BaseLLMSuccessResponse(BaseModel, Generic[T]):
    """全局统一成功响应结构 (code: 100000-299999)"""

    code: int = Field(100000, description="业务状态码")
    data: T | None = Field(None, description="成功业务数据")


class BaseLLMFailedResponse(BaseModel, Generic[F]):
    """全局统一失败响应结构 (code: 300000-499999)"""

    code: int = Field(300000, description="业务状态码")
    data: F | None = Field(None, description="失败业务数据")


# ================= 2. 业务数据基类 =================


class BaseLLMSuccessData(BaseModel):
    # ...:必填字段，无默认值
    data: Any = Field(..., description="返回llm结果，为LLM输出的结构化json对象")


class BaseLLMFailedData(BaseModel):
    """全局失败业务数据基类：可放全局通用的错误附加信息"""

    error_msg: str = Field(..., description="全局错误描述")


StreamDataT = TypeVar("StreamDataT")


class StreamMessage(BaseModel, Generic[StreamDataT]):
    """SSE单条消息基础封装 —— 事件类型由 SSE 协议外层 event: 字段决定，不嵌入 JSON"""

    code: int
    data: StreamDataT | None = None


# 增量分片数据模型 —— 统一用 content 承载文本，事件类型区分语义
#   event: delta   → data: {"content":"你"}      回答内容
#   event: thinking → data: {"content":"让我想想..."}  思考过程
class ChatDeltaData(BaseModel):
    content: str = ""


# 空结束数据
class ChatDoneData(BaseModel):
    # `extra="forbid"`：**禁止传入模型定义之外的字段**。
    # 如果前端 / 传入的 json 多了任何没有在这个 Model 里定义的 key，直接抛校验异常，请求报错。
    class Config:
        extra = "forbid"


# SSE start 事件携带的元信息
class ChatStartData(BaseModel):
    msgId: str = Field(..., description="本次回答的消息 id")
    conversationId: str = Field(..., description="会话 id")
    model: str = Field(..., description="本次使用的模型")
    createdAt: int = Field(..., description="开始时间戳 (Unix 秒)")
    traceId: str = Field(..., description="链路追踪 id")
