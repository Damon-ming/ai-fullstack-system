"""从 model-gateway 读取模型规格。"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


def load_model_config(
    inference_base_url: str,
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """启动时请求 gateway 的内部模型配置接口。"""
    parsed = urlsplit(inference_base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("推理网关地址必须是有效的 HTTP(S) URL")
    endpoint = urlunsplit(
        (parsed.scheme, parsed.netloc, "/internal/model-config", "", "")
    )
    request = Request(endpoint)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"无法从 model-gateway 读取模型配置: {type(exc).__name__}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), dict):
        raise TypeError("model-gateway 模型配置响应格式无效")
    for model_name, model_config in payload["models"].items():
        if not isinstance(model_name, str) or not isinstance(model_config, dict):
            raise TypeError("model-gateway 模型配置项格式无效")
        max_model_len = model_config.get("max_model_len")
        if type(max_model_len) is not int or max_model_len < 2:
            raise ValueError(
                f"model-gateway models.{model_name}.max_model_len 配置无效"
            )
        if "dimension" in model_config:
            dimension = model_config["dimension"]
            if type(dimension) is not int or dimension <= 0:
                raise ValueError(
                    f"model-gateway models.{model_name}.dimension 配置无效"
                )
    return payload["models"]
