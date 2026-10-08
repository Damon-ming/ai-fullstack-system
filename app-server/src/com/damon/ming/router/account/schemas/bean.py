from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    """申请 Token 请求体。"""

    # TODO: 后期替换为手机号，当前用设备唯一 ID 作为入参
    device_id: str = Field(
        ...,
        description="设备唯一标识（必填），用于关联 token 与设备。TODO: 后期替换为手机号",
    )


class TokenResponseData(BaseModel):
    """Token 响应数据。"""

    token: str = Field(..., description="服务端生成的设备认证令牌")
