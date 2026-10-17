# app-server/src/com/damon/ming/app/config/db_config_loader.py
"""
数据库配置加载器 —— 从 YAML 文件读取连接参数。

本模块属于 app/ 业务层，不属于 db/ 模块。
db/ 模块通过 DbConfig 数据类接收参数，不感知配置来源。

配置来源：
  - 仅从 YAML 文件读取，不支持环境变量覆盖
  - 加载失败（文件不存在、格式错误、剖面缺失）直接抛出异常

支持多剖面（default / production），通过 profile 参数选择。
"""

import os

import yaml


class DbConfigLoader:
    """从 YAML 文件加载数据库配置。

    用法：
        cfg = DbConfigLoader().load()                    # 默认剖面
        cfg = DbConfigLoader().load(profile="production") # 生产剖面
        cfg = DbConfigLoader("path/to/config.yaml").load()
    """

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "db-config.yaml")
        self._config_path = config_path

    def load(self, profile: str = "common"):
        """加载指定剖面的配置，返回 DbConfig。

        加载失败时直接抛出异常（FileNotFoundError / ValueError），
        调用方必须处理，不做静默降级。
        """
        from src.com.damon.ming.db.db_config import DbConfig

        raw = self._read_yaml(profile)

        return DbConfig(
            host=raw.get("host", ""),
            port=int(raw.get("port", 5432)),
            dbname=raw.get("dbname", ""),
            user=raw.get("user", ""),
            password=raw.get("password", ""),
            dialect=raw.get("dialect", "postgresql"),
            driver=raw.get("driver", ""),
            retry_count=int(raw.get("retry", 3)),
            backoff_seconds=float(raw.get("backoff", 0.1)),
            pool_size=int(raw.get("pool_size", 5)),
            max_overflow=int(raw.get("max_overflow", 10)),
            engine_kwargs=self._build_engine_kwargs(raw),
        )

    # ---- 私有 -------------------------------------------------------------

    def _read_yaml(self, profile: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"DB 配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or "db" not in raw_cfg:
            raise ValueError("DB 配置文件格式错误：缺少 'db' 根节点")
        section = raw_cfg["db"].get(profile, {})
        if not section:
            raise ValueError(f"DB 配置文件中未找到剖面: {profile}")
        return section

    @staticmethod
    def _build_engine_kwargs(raw: dict) -> dict:
        """构建 SQLAlchemy engine 的额外连接参数。"""
        kwargs: dict = {}
        timeout = raw.get("connect_timeout", None)
        if timeout is not None:
            kwargs["connect_args"] = {"connect_timeout": int(timeout)}
        return kwargs
