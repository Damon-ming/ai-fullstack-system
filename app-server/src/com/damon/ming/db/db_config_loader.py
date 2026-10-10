# app-server/src/com/damon/ming/db/db_config_loader.py
"""
数据库配置加载器 —— 从 YAML 文件读取连接参数。

加载优先级：
  1. 显式传入的 config_path
  2. DB_CONFIG_PATH 环境变量
  3. 默认路径：本目录下的 db-config.yaml

支持多剖面（default / production），通过 profile 参数选择。
"""

import os
from typing import Any

import yaml

from src.com.damon.ming.db.db_config import DbConfig


class DbConfigLoader:
    """从 YAML 文件加载数据库配置。

    用法：
        cfg = DbConfigLoader().load()                    # 默认剖面
        cfg = DbConfigLoader().load(profile="production") # 生产剖面
        cfg = DbConfigLoader("path/to/config.yaml").load()
    """

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = os.environ.get("DB_CONFIG_PATH", "")
        if not config_path:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "db-config.yaml")
        self._config_path = config_path

    def load(self, profile: str = "default") -> DbConfig:
        """加载指定剖面的配置，返回 DbConfig。

        环境变量覆盖规则：
          DB_HOST、DB_PORT、DB_NAME、DB_USER、DB_PASSWORD
          若设置，优先于 YAML 中的值。
        """
        raw = self._read_yaml(profile)
        return DbConfig(
            host=self._env_or_value("DB_HOST", raw.get("host", "localhost")),
            port=int(self._env_or_value("DB_PORT", raw.get("port", 5432))),
            dbname=self._env_or_value("DB_NAME", raw.get("dbname", "")),
            user=self._env_or_value("DB_USER", raw.get("user", "")),
            password=self._env_or_value("DB_PASSWORD", raw.get("password", "")),
            connect_kwargs=self._build_connect_kwargs(raw),
        )

    def get_pool_settings(self, profile: str = "default") -> dict[str, Any]:
        """获取连接池设置（pool_min, pool_max）。"""
        raw = self._read_yaml(profile)
        return {
            "min_conn": int(raw.get("pool_min", 1)),
            "max_conn": int(raw.get("pool_max", 10)),
        }

    def get_retry_settings(self, profile: str = "default") -> int:
        """获取重试次数。"""
        raw = self._read_yaml(profile)
        return int(raw.get("retry", 3))

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self, profile: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"DB 配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or "db" not in raw_cfg:
            raise ValueError(f"DB 配置文件格式错误：缺少 'db' 根节点")
        section = raw_cfg["db"].get(profile, {})
        if not section:
            raise ValueError(f"DB 配置文件中未找到剖面: {profile}")
        return section

    @staticmethod
    def _env_or_value(env_key: str, yaml_value: Any) -> str:
        """环境变量优先，否则用 YAML 值。"""
        env_val = os.environ.get(env_key, "")
        return env_val if env_val else str(yaml_value)

    @staticmethod
    def _build_connect_kwargs(raw: dict) -> dict:
        """构建额外的 psycopg2 连接参数。"""
        kwargs = {}
        timeout = raw.get("connect_timeout", None)
        if timeout is not None:
            kwargs["connect_timeout"] = int(timeout)
        return kwargs
