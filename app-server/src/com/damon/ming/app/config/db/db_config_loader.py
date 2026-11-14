# app-server/src/com/damon/ming/app/config/db/db_config_loader.py
"""
数据库配置加载器 —— 从 YAML 文件读取连接参数，环境变量优先覆盖。

本模块属于 app/ 业务层，不属于 db/ 模块。
db 模块通过 DbConfig 数据类接收参数，不感知配置来源。

配置来源（优先级从高到低）：
  1. 环境变量（DB_ 前缀 + YAML 字段名大写，如 name → DB_NAME）
  2. YAML 文件
  3. 无默认值 —— 缺失任何必填字段直接报错

设计原则：
  - 所有必填字段无默认值，缺失或为空立即终止启动
  - 不做静默降级 —— 错误的默认值比启动失败更危险
"""

import os

from src.com.damon.ming.app.config._yaml import load_yaml
from src.com.damon.ming.app.config.env import get_db_override


class DbConfigLoader:
    """从 YAML 文件加载数据库配置，环境变量优先覆盖。

    用法：
        cfg = DbConfigLoader().load()
    """

    # 必填字段（字段名大写即为环境变量名）
    KEYS = (
        "host",
        "port",
        "name",
        "user",
        "password",
        "dialect",
        "pool_size",
        "max_overflow",
        "pool_timeout",
        "pool_recycle",
        "retry",
        "backoff",
    )

    # 布尔可选字段（YAML 缺失或 DB_ECHO 未设置时取 False）
    BOOL_KEYS = ("echo",)

    def __init__(self):
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self):
        """加载配置，环境变量优先覆盖，返回 DbConfig。

        必填字段缺失或为空直接抛出异常，不做静默降级。
        """
        from src.com.damon.ming.db.db_config import DbConfig

        raw = self._read_yaml()

        # 合并：环境变量 > YAML（环境变量名 = DB_ + 字段名大写）
        merged = dict(raw)
        for key in self.KEYS:
            env_value = get_db_override(key)
            if env_value is not None:
                merged[key] = env_value
        for key in self.BOOL_KEYS:
            env_value = get_db_override(key)
            if env_value is not None:
                merged[key] = env_value

        # 校验必填字段（用 is None 判断，避免 0 被真值检查误判为缺失）
        missing = [f for f in self.KEYS if merged.get(f) is None or merged.get(f) == ""]
        if missing:
            raise ValueError(
                f"数据库配置缺少必填字段，请检查环境变量或 YAML：{', '.join(missing)}"
            )

        return DbConfig(
            host=merged["host"],
            port=int(merged["port"]),
            dbname=merged["name"],
            user=merged["user"],
            password=merged["password"],
            dialect=merged["dialect"],
            driver=merged.get("driver", ""),
            retry_count=int(merged["retry"]),
            backoff_seconds=float(merged["backoff"]),
            pool_size=int(merged["pool_size"]),
            max_overflow=int(merged["max_overflow"]),
            pool_timeout=int(merged["pool_timeout"]),
            pool_recycle=int(merged["pool_recycle"]),
            echo=self._as_bool(merged.get("echo", False)),
            engine_kwargs=self._build_engine_kwargs(merged),
        )

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)

    @staticmethod
    def _as_bool(value: object) -> bool:
        """只接受布尔值或 true/false 字符串，配置错误直接抛异常。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "true":
                return True
            if normalized == "false":
                return False
        raise ValueError("数据库布尔配置必须为 true 或 false，请检查 YAML 或环境变量")

    @staticmethod
    def _build_engine_kwargs(raw: dict) -> dict:
        """构建 SQLAlchemy engine 的额外连接参数。"""
        kwargs: dict = {}
        timeout = raw.get("connect_timeout")
        if timeout is not None:
            kwargs["connect_args"] = {"connect_timeout": int(timeout)}
        return kwargs
