from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """申请 Token 请求体。"""

    # TODO: 当前用随机模拟手机号，后期替换为用户真实输入的手机号
    phone: str = Field(
        ...,
        description="手机号（含区号），用于标识用户身份。TODO: 当前模拟",
        examples=["+8613800138000"],
    )


class TokenResponseData(BaseModel):
    """Token 响应数据。"""

    token: str = Field(..., description="服务端生成的用户身份令牌")
    device_id: str = Field(..., description="服务端根据 UA 计算的设备唯一标识")
