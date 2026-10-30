# app-server/src/com/damon/ming/db/db_config.py
"""
数据库连接配置 —— 纯数据类，无环境变量兜底。

所有参数由外部调用方传入（如 DbConfigLoader 从 YAML 加载后构造），
db 模块本身不感知配置来源，也不做任何环境变量回退。

支持多数据库后端（PostgreSQL / MySQL / SQLite 等），通过 SQLAlchemy URL 格式区分：
  - postgresql://user:pass@host:port/dbname
  - mysql+pymysql://user:pass@host:port/dbname
  - sqlite:///path/to/db.sqlite
"""

from dataclasses import dataclass, field
from typing import Literal

# 支持的数据库驱动方言
DbDialect = Literal["postgresql", "mysql", "sqlite"]


@dataclass(frozen=True)
class DbConfig:
    """数据库连接配置（纯数据类）。

    所有参数由上层配置传入，db 模块内不含任何环境变量读取逻辑。

    用法：
      # 方式一：完整 SQLAlchemy URL
      cfg = DbConfig(url="postgresql://...", retry_count=3, backoff_seconds=0.1)

      # 方式二：拆解参数
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
    retry_count: int = 3  # 连接失败重试次数
    backoff_seconds: float = 0.1  # 重试退避基础秒数（实际睡眠 = backoff * (attempt+1)）
    pool_size: int = 5  # 连接池大小
    max_overflow: int = 10  # 超出 pool_size 的额外连接数（最大 15 并发）
    # 注意：document_pool / retrieval_pool / bm25_pool 操作 pgvector，
    # 不占用本连接池。主池仅服务账号、会话、审计、历史等短事务（毫秒级），
    # 15 连接可支撑 ~3000 TPS，GPU 推理才是真正的吞吐瓶颈。
    # 若遇连接等待，优先排查长事务而非调大池子。
    pool_timeout: int = 30  # 获取连接的超时秒数
    pool_recycle: int = 3600  # 连接回收秒数（防止连接被数据库断开）
    echo: bool = False  # 是否打印 SQL 调试日志

    # SQLAlchemy engine 额外参数（传递给 create_engine 的额外 kwargs）
    engine_kwargs: dict = field(default_factory=dict)

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
