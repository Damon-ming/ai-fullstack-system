# app-server/src/com/damon/ming/db/db_config.py
"""
数据库连接配置 —— 纯数据类 + 环境变量读取。

支持多数据库后端（PostgreSQL / MySQL / SQLite 等），通过 SQLAlchemy URL 格式区分：
  - postgresql://user:pass@host:port/dbname
  - mysql+pymysql://user:pass@host:port/dbname
  - sqlite:///path/to/db.sqlite

安全说明：
  - 密码通过环境变量注入，不落代码
  - URL 支持完整字符串或拆解参数两种方式
"""

import os
from dataclasses import dataclass, field
from typing import Literal


# 支持的数据库驱动方言
DbDialect = Literal["postgresql", "mysql", "sqlite"]


@dataclass(frozen=True)
class DbConfig:
    """数据库连接配置（纯数据类）。

    所有技术策略参数（重试次数、退避秒数）均由上层配置，
    db 模块内不含任何硬编码的业务/技术默认值。

    用法：
      # 方式一：完整 SQLAlchemy URL + 显式策略参数
      cfg = DbConfig(url="postgresql://...", retry_count=3, backoff_seconds=0.1)

      # 方式二：从环境变量自动组装
      cfg = DbConfig.from_env()

      # 方式三：显式参数（默认 PostgreSQL）
      cfg = DbConfig(host="localhost", port=5432, dbname="mydb", user="pg", password="secret")
    """

    # ---- 连接信息 -------------------------------------------------------
    url: str = ""  # SQLAlchemy 完整 URL（优先级最高）
    host: str = ""
    port: int = 5432
    dbname: str = ""
    user: str = ""
    password: str = ""
    dialect: DbDialect = "postgresql"  # postgresql | mysql | sqlite
    driver: str = ""  # 驱动名（如 pymysql、psycopg2），空则用默认

    # ---- 技术策略参数（上层可配置，不传则使用最小安全值）-------------------
    retry_count: int = 3          # 连接失败重试次数
    backoff_seconds: float = 0.1  # 重试退避基础秒数（实际睡眠 = backoff * (attempt+1)）
    pool_size: int = 5            # 连接池大小
    max_overflow: int = 10        # 超出 pool_size 的额外连接数
    pool_timeout: int = 30        # 获取连接的超时秒数
    pool_recycle: int = 3600      # 连接回收秒数（防止连接被数据库断开）
    echo: bool = False            # 是否打印 SQL 调试日志

    # SQLAlchemy engine 额外参数（传递给 create_engine 的额外 kwargs）
    engine_kwargs: dict = field(default_factory=dict)

    @staticmethod
    def from_env(prefix: str = "DB_") -> "DbConfig":
        """从环境变量读取配置。

        环境变量：
          {prefix}URL       — 完整 SQLAlchemy URL（优先级最高）
          {prefix}DIALECT   — 数据库方言：postgresql / mysql / sqlite
          {prefix}DRIVER    — 驱动名（如 pymysql、psycopg2）
          {prefix}HOST      — 主机名
          {prefix}PORT      — 端口
          {prefix}NAME      — 数据库名（或 SQLite 文件路径）
          {prefix}USER      — 用户名
          {prefix}PASSWORD  — 密码
          {prefix}RETRY     — 重试次数
          {prefix}BACKOFF   — 退避基础秒数
          {prefix}POOL_SIZE — 连接池大小
          {prefix}MAX_OVERFLOW — 额外连接数
        """
        url = os.environ.get(f"{prefix}URL", "")
        if url:
            return DbConfig(
                url=url,
                retry_count=int(os.environ.get(f"{prefix}RETRY", "3")),
                backoff_seconds=float(os.environ.get(f"{prefix}BACKOFF", "0.1")),
                pool_size=int(os.environ.get(f"{prefix}POOL_SIZE", "5")),
                max_overflow=int(os.environ.get(f"{prefix}MAX_OVERFLOW", "10")),
                dialect=os.environ.get(f"{prefix}DIALECT", _dialect_from_url(url)),  # type: ignore
            )

        dialect_name = os.environ.get(f"{prefix}DIALECT", "postgresql")
        return DbConfig(
            host=os.environ.get(f"{prefix}HOST", ""),
            port=int(os.environ.get(f"{prefix}PORT", "5432")),
            dbname=os.environ.get(f"{prefix}NAME", ""),
            user=os.environ.get(f"{prefix}USER", ""),
            password=os.environ.get(f"{prefix}PASSWORD", ""),
            dialect=dialect_name,  # type: ignore
            driver=os.environ.get(f"{prefix}DRIVER", ""),
            retry_count=int(os.environ.get(f"{prefix}RETRY", "3")),
            backoff_seconds=float(os.environ.get(f"{prefix}BACKOFF", "0.1")),
            pool_size=int(os.environ.get(f"{prefix}POOL_SIZE", "5")),
            max_overflow=int(os.environ.get(f"{prefix}MAX_OVERFLOW", "10")),
        )

    def get_sqlalchemy_url(self) -> str:
        """获取 SQLAlchemy 引擎 URL。"""
        if self.url:
            return self.url

        # SQLite 特殊处理
        if self.dialect == "sqlite":
            return f"sqlite:///{self.dbname}"

        driver_part = f"+{self.driver}" if self.driver else ""
        auth = f"{self.user}:{self.password}" if self.password else self.user
        host = self.host or "localhost"
        return f"{self.dialect}{driver_part}://{auth}@{host}:{self.port}/{self.dbname}"

    def get_engine_kwargs(self) -> dict:
        """获取 SQLAlchemy create_engine 的 kwargs。"""
        kwargs: dict = {
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "echo": self.echo,
        }
        kwargs.update(self.engine_kwargs)
        return kwargs


def _dialect_from_url(url: str) -> DbDialect:
    """从 URL 中提取方言类型。"""
    lower = url.lower()
    if lower.startswith("postgresql") or lower.startswith("postgres"):
        return "postgresql"
    if lower.startswith("mysql"):
        return "mysql"
    if lower.startswith("sqlite"):
        return "sqlite"
    return "postgresql"
