import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    name: str | None = Field(
        None,
        max_length=64,
        description="首次注册必填的姓名；已有账号登录可省略",
    )

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return _validate_password(v)

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("姓名不能为空")
        return value


class TokenResponseData(BaseModel):
    """Token 响应数据。"""

    token: str = Field(..., description="该设备的登录凭据，连续 7 天未使用则失效")
    is_new: bool = Field(
        False, description="本次是否为新注册用户（false = 已有用户登录）"
    )


class ProfileResponseData(BaseModel):
    """用户资料响应数据。"""

    user_id: int = Field(..., ge=100000, le=999999, description="六位用户编号")
    name: str = Field(..., description="首次注册时填写的姓名")
    nickname: str = Field(..., description="可修改的昵称")


class UpdateProfileResponseData(BaseModel):
    """昵称更新响应。"""

    nickname: str = Field(..., description="更新后的昵称")


class UpdateProfileRequest(BaseModel):
    """昵称更新请求；用户编号不接受客户端修改。"""

    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(..., min_length=1, max_length=64, description="新昵称")

    @field_validator("nickname")
    @classmethod
    def _check_nickname(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("昵称不能为空")
        return value
