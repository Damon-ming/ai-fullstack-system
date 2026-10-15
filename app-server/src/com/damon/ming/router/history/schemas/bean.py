from pydantic import BaseModel, Field
from src.com.damon.ming.schemas.request import BaseBizRequest
from src.com.damon.ming.schemas.response import BaseBizFailedData, BaseBizSuccessData


# ================= 1. 请求 =================
class HistoryListRequest(BaseBizRequest):
    """历史记录列表请求：分页参数"""

    page: int = Field(1, ge=1, description="页码（从1开始）")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")


class HistorySaveRequest(BaseBizRequest):
    """保存/更新对话历史请求"""

    title: str = Field(..., max_length=200, description="对话标题（首条用户消息截取）")
    messages: list[dict] = Field(
        default_factory=list, description="消息列表 [{id,text,role}]"
    )


# ================= 2. 成功数据 =================
class HistoryMessageItem(BaseModel):
    id: str = Field(..., description="消息唯一标识")
    text: str = Field(..., description="消息正文")
    role: str = Field(..., description="角色: user | assistant")


class HistoryListItem(BaseModel):
    """历史记录列表项（不含消息正文，节省传输）"""

    id: str = Field(..., description="对话唯一标识")
    title: str = Field(..., description="对话标题")
    msg_count: int = Field(0, description="消息条数")
    created_at: str = Field("", description="创建时间 ISO8601")
    updated_at: str = Field("", description="更新时间 ISO8601")


class HistoryDetailData(HistoryListItem):
    """历史记录详情（含消息正文）"""

    messages: list[HistoryMessageItem] = Field(
        default_factory=list, description="消息列表"
    )


class HistoryListSuccessData(BaseBizSuccessData):
    """历史记录列表成功数据"""

    items: list[HistoryListItem] = Field(
        default_factory=list, description="历史记录列表"
    )
    total: int = Field(0, description="总条数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(20, description="每页条数")


class HistorySaveSuccessData(BaseBizSuccessData):
    """保存历史记录成功数据"""

    conversation: HistoryDetailData = Field(..., description="保存后的对话详情")


class HistoryDeleteSuccessData(BaseBizSuccessData):
    """删除历史记录成功数据"""

    deleted_id: str = Field(..., description="已删除的对话 ID")


# ================= 3. 失败数据 =================
class HistoryFailedData(BaseBizFailedData):
    """历史记录通用失败数据"""

    pass
