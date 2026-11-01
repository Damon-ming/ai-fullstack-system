from pydantic import BaseModel, Field
from src.com.damon.ming.schemas.response import BaseBizSuccessData


# ================= 1. 文件上传响应 =================
class FileUploadItem(BaseModel):
    """成功文件"""

    filename: str = Field(..., description="原始文件名")
    file_uid: str = Field(..., description="服务端文件唯一 ID（后续删除/引用用）")


class FileUploadFailedItem(BaseModel):
    """失败文件"""

    filename: str = Field(..., description="原始文件名")
    error: str = Field(..., description="失败原因")


class FileUploadResponse(BaseBizSuccessData):
    """文件上传响应：成功列表 + 失败列表"""

    files: list[FileUploadItem] = Field(
        default_factory=list, description="成功处理的文件列表"
    )
    failed_files: list[FileUploadFailedItem] = Field(
        default_factory=list, description="处理失败的文件列表，客户端应提示重试"
    )
