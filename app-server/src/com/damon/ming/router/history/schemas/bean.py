from pydantic import BaseModel, Field
from src.com.damon.ming.schemas.request import BaseBizRequest
from src.com.damon.ming.schemas.response import BaseBizFailedData


# ================= 1. 请求 =================
class HistoryListRequest(BaseBizRequest):
    """历史记录列表请求：分页参数"""

    page: int = Field(1, ge=1, description="页码（从1开始）")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")


class HistoryTurnInput(BaseModel):
    """客户端保存的一轮问答（token 级时刻无法观测，由服务端盖章）"""

    query: str = Field(..., description="用户提问")
    content: str = Field(..., description="助手回答正文")
    reasoning: str = Field("", description="推理过程（未开启推理时为空）")


class HistorySaveRequest(BaseBizRequest):
    """保存会话请求"""

    conversation_id: str | None = Field(None, description="会话 ID（缺省则新建）")
    title: str = Field(..., max_length=200, description="对话标题（首条用户消息截取）")
    turns: list[HistoryTurnInput] = Field(default_factory=list, description="轮次列表")


# ================= 2. 成功数据 =================
class HistoryTurnItem(BaseModel):
    """一轮问答（含四个时间点，时长由查询方派生）"""

    turn_id: str = Field(..., description="轮次唯一标识")
    query: str = Field(..., description="用户提问")
    reasoning: str = Field("", description="推理过程（未开启推理时为空）")
    content: str = Field(..., description="助手回答正文")
    query_at: str = Field("", description="提问时间 ISO8601")
    first_token_at: str = Field(
        "", description="首个 token 时间 ISO8601（非流式调用为空）"
    )
    reasoning_done_at: str = Field(
        "", description="推理结束时间 ISO8601（未开启推理为空）"
    )
    answered_at: str = Field("", description="回答完成时间 ISO8601")


class HistoryListItem(BaseModel):
    """会话列表项（不含轮次正文，节省传输）"""

    id: str = Field(..., description="会话唯一标识")
    title: str = Field(..., description="对话标题")
    created_at: str = Field("", description="创建时间 ISO8601")
    updated_at: str = Field("", description="更新时间 ISO8601")


class HistoryDetailData(HistoryListItem):
    """会话详情（含全部轮次，按提问时间升序）"""

    turns: list[HistoryTurnItem] = Field(default_factory=list, description="轮次列表")


# ================= 3. 失败数据 =================
class HistoryFailedData(BaseBizFailedData):
    """历史记录通用失败数据"""
