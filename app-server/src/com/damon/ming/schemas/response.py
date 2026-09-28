from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# 定义泛型，用于包裹具体的业务数据
T = TypeVar("T")
F = TypeVar("F")


# ================= 1. 响应外壳 =================
class BaseSuccessResponse(BaseModel, Generic[T]):
    """全局统一成功响应结构 (bizCode: 10000-39999)"""

    bizCode: int = Field(20000, description="业务状态码")
    data: T | None = Field(None, description="成功业务数据")


class BaseFailedResponse(BaseModel, Generic[F]):
    """全局统一失败响应结构 (bizCode: 40000-50000)"""

    bizCode: int = Field(40000, description="业务状态码")
    data: F | None = Field(None, description="失败业务数据")


# ================= 2. 业务数据基类 =================
class BaseBizSuccessData(BaseModel):
    result: Any = Field(..., description="返回结果，为业务输出的结构化json对象")


class BaseBizFailedData(BaseModel):
    """全局失败业务数据基类：可放全局通用的错误附加信息"""

    error_msg: str = Field(..., description="全局错误描述")
