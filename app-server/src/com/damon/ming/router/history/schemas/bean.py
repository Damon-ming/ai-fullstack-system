from pydantic import BaseModel, Field
from src.com.damon.ming.schemas.response import BaseBizFailedData


# ================= 1. 成功数据 =================
# 字段命名与前端 ChatMessage/HistoryTurn 保持同一套词汇
class HistoryTurnItem(BaseModel):
    """一轮问答（含四个时间点，时长由查询方派生）"""

    turnId: str = Field(..., description="轮次唯一标识")
    query: str = Field(..., description="用户提问")
    reasoning: str = Field("", description="推理过程（未开启推理时为空）")
    content: str = Field(..., description="助手回答正文")
    errorMsg: str = Field("", description="本轮异常提示（用户可见文案，成功时为空）")
    queryAt: str = Field("", description="提问时间 ISO8601")
    firstTokenAt: str = Field(
        "", description="首个 token 时间 ISO8601（非流式调用为空）"
    )
    reasoningDoneAt: str = Field(
        "", description="推理结束时间 ISO8601（未开启推理为空）"
    )
    answeredAt: str = Field("", description="回答完成时间 ISO8601")


class HistoryListItem(BaseModel):
    """会话列表项（不含轮次正文，节省传输）"""

    conversationId: str = Field(..., description="会话唯一标识")
    title: str = Field(..., description="对话标题")
    createdAt: str = Field("", description="创建时间 ISO8601")
    updatedAt: str = Field("", description="更新时间 ISO8601")


class HistoryDetailData(HistoryListItem):
    """会话详情（含全部轮次，按提问时间升序）"""

    turns: list[HistoryTurnItem] = Field(default_factory=list, description="轮次列表")


# ================= 2. 失败数据 =================
class HistoryFailedData(BaseBizFailedData):
    """历史记录通用失败数据"""
