# app-server/src/com/damon/ming/app/config/env.py
"""环境变量读取入口 —— 集中应用配置的环境变量读取与解析。

本模块是环境变量名的唯一定义点：变量名字符串只在这里出现，
其他模块一律通过 getter 取用，避免同一变量名散落到多处后难以查找。

职责边界：
  - 只读取，不做业务校验（MASTER_KEY 长度校验由 precheck 负责）
  - 密钥类（MASTER_KEY）用 getter 而非模块级常量，避免被广泛 import 后泄漏
  - DB_* / INFERENCE_* 也由本模块读取，YAML 合并和业务校验仍由各 loader 负责
"""

import json
import os

# ── 变量名（集中定义，唯一出处）────────────────────────────────────────
_VAR_MASTER_KEY = "MASTER_KEY"
_VAR_APP_ENV = "APP_ENV"
_VAR_CORS_ORIGINS = "CORS_ORIGINS"
_VAR_LOG_LEVEL = "LOG_LEVEL"
_VAR_DB_PREFIX = "DB_"
_VAR_INFERENCE_SERVER = "INFERENCE_SERVER"
_VAR_INFERENCE_GATEWAY_URL = "INFERENCE_GATEWAY_URL"
_VAR_INFERENCE_TIMEOUT = "INFERENCE_TIMEOUT"
_VAR_INFERENCE_API_KEYS = "INFERENCE_API_KEYS"
_VAR_INFERENCE_API_KEY_PREFIX = "INFERENCE_API_KEY_"

# APP_ENV 取值
ENV_DEBUG = "debug"
ENV_RELEASE = "release"

# LOG_LEVEL 默认值
DEFAULT_LOG_LEVEL = "INFO"


def get_master_key() -> str:
    """加密主密钥（必填，无默认值）。

    读取后注入 encryption 模块派生 KEK；启动前由 precheck 校验长度。
    """
    return os.environ.get(_VAR_MASTER_KEY, "")


def get_app_env() -> str:
    """环境标志：debug / release（默认 debug，已归一化为小写）。"""
    return os.environ.get(_VAR_APP_ENV, ENV_DEBUG).lower()


def get_cors_origins() -> list[str]:
    """Release 模式 CORS 允许来源（逗号分隔），已去除空白项。"""
    raw = os.environ.get(_VAR_CORS_ORIGINS, "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_log_level() -> str:
    """日志级别：DEBUG / INFO / WARNING / ERROR / CRITICAL。

    默认 INFO，已归一化为大写。未知值由调用方（log 模块）回退处理。
    """
    return os.environ.get(_VAR_LOG_LEVEL, DEFAULT_LOG_LEVEL).upper()


def get_db_override(field: str) -> str | None:
    """读取 DB_ + 字段名大写的覆盖值，未设置返回 None，保留空字符串供 loader 校验。"""
    return os.environ.get(f"{_VAR_DB_PREFIX}{field.upper()}")


def get_inference_server() -> str:
    """推理后端类型，默认 ollama。"""
    return os.environ.get(_VAR_INFERENCE_SERVER, "ollama")


def get_inference_gateway_url() -> str:
    """推理网关地址。"""
    return os.environ.get(
        _VAR_INFERENCE_GATEWAY_URL, "http://inference-gateway:8080/v1"
    )


def get_inference_timeout() -> float:
    """推理超时秒数，默认 180；无效数字直接抛异常。"""
    return float(os.environ.get(_VAR_INFERENCE_TIMEOUT, "180"))


def get_inference_api_keys() -> dict[str, str]:
    """解析角色密钥：非空单角色变量优先于批量 JSON，不设置默认密钥。

    保持既有行为：JSON 语法错误时忽略批量值，缺失角色由 loader 校验。
    """
    keys: dict[str, str] = {}
    json_str = os.environ.get(_VAR_INFERENCE_API_KEYS, "")
    if json_str:
        try:
            keys.update(json.loads(json_str))
        except json.JSONDecodeError:
            pass

    for env_key, env_val in os.environ.items():
        if env_key.startswith(_VAR_INFERENCE_API_KEY_PREFIX) and env_val:
            role = env_key[len(_VAR_INFERENCE_API_KEY_PREFIX) :].lower()
            keys[role] = env_val
    return keys
