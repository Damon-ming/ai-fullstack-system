"""Internal role parameters used by inference routing and request budgets."""

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class InferenceRoleParams:
    model_name: str
    api_key: str
    options: dict[str, Any]
    timeout_seconds: float | None
    max_model_len: int

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key 必须是非空字符串")
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name 必须是非空字符串")
        if type(self.max_model_len) is not int or self.max_model_len < 2:
            raise ValueError("max_model_len 必须是大于等于 2 的整数")
        if self.timeout_seconds is not None and (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds 必须是有限正数")
        if not isinstance(self.options, dict):
            raise TypeError("options 必须是键值对")
        if "max_tokens" in self.options and (
            type(self.options["max_tokens"]) is not int
            or self.options["max_tokens"] < 1
        ):
            raise ValueError("options.max_tokens 必须是正整数")
        for field, lower, upper in (("temperature", 0, 2), ("top_p", 0, 1)):
            if field in self.options:
                value = self.options[field]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not lower <= value <= upper
                    or (field == "top_p" and value == 0)
                ):
                    raise ValueError(f"options.{field} 超出有效数值范围")
