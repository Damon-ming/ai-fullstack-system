# app-server/src/com/damon/ming/app/config/env.py
"""裸环境变量读取入口 —— 集中没有 YAML 归属的环境变量。

本模块是环境变量名的唯一定义点：变量名字符串只在这里出现，
其他模块一律通过 getter 取用，避免同一变量名散落到多处后难以查找。

职责边界：
  - 只读取，不做业务校验（MASTER_KEY 长度校验由 precheck 负责）
  - 密钥类（MASTER_KEY）用 getter 而非模块级常量，避免被广泛 import 后泄漏
  - 带 YAML 归属的变量（DB_* / INFERENCE_*）仍在各自 loader 中读取，
    它们已有「YAML 为主、环境变量覆盖」的内聚单元，不纳入本模块
"""

import os

# ── 变量名（集中定义，唯一出处）────────────────────────────────────────
_VAR_MASTER_KEY = "MASTER_KEY"
_VAR_APP_ENV = "APP_ENV"
_VAR_CORS_ORIGINS = "CORS_ORIGINS"
_VAR_LOG_LEVEL = "LOG_LEVEL"

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
