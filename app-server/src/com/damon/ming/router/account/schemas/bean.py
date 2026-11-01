import re

from pydantic import BaseModel, Field, field_validator

_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[._]).{8,64}$")


def _validate_password(value: str) -> str:
    """校验密码强度：≥8 位，含大小写字母、数字、. 或 _ 至少一个。"""
    if not _PASSWORD_PATTERN.match(value):
        raise ValueError(
            "密码至少 8 位，需同时包含大写字母、小写字母、数字，以及 . 或 _ 中至少一个"
        )
    return value


class LoginRequest(BaseModel):
    """登录请求体。"""

    phone: str = Field(
        ...,
        pattern=r"^\+?[0-9]{6,20}$",
        description="手机号（含区号），6-20 位数字，可选 + 前缀。如 +8613800138000",
        examples=["+8613800138000"],
    )
    password: str = Field(
        ...,
        description="登录密码：≥8 位，含大小写字母、数字、. 或 _ 至少一个",
        examples=["Abc123_456"],
    )

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return _validate_password(v)


class TokenResponseData(BaseModel):
    """Token 响应数据。"""

    token: str = Field(..., description="服务端生成的用户身份令牌")
    device_id: str = Field(..., description="服务端根据 UA 计算的设备唯一标识")
    session_id: str = Field(..., description="本次 token + device 组合的会话标识")
    is_new: bool = Field(
        False, description="本次是否为新注册用户（false = 已有用户登录）"
    )


class ProfileResponseData(BaseModel):
    """用户资料响应数据。"""

    name: str = Field(..., description="用户昵称")
