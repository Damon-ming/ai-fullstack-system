# app-server/src/com/damon/ming/db/db_config.py
"""
数据库连接配置 —— 纯数据类 + 环境变量读取。

安全说明：
  - 密码通过环境变量注入，不落代码
  - connection_string 支持完整 URL 或拆解参数两种方式
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DbConfig:
    """数据库连接配置（纯数据类）。

    所有技术策略参数（重试次数、退避秒数）均由上层配置，
    db 模块内不含任何硬编码的业务/技术默认值。

    用法：
      # 方式一：完整连接字符串 + 显式策略参数
      cfg = DbConfig(connection_string="postgresql://...", retry_count=3, backoff_seconds=0.1)

      # 方式二：从环境变量自动组装
      cfg = DbConfig.from_env()

      # 方式三：显式参数
      cfg = DbConfig(host="localhost", port=5432, dbname="mydb", user="pg", password="secret")
    """

    # ---- 连接信息 -------------------------------------------------------
    connection_string: str = ""
    host: str = ""
    port: int = 5432
    dbname: str = ""
    user: str = ""
    password: str = ""

    # ---- 技术策略参数（上层可配置，不传则使用最小安全值）-------------------
    retry_count: int = 3          # 连接失败重试次数
    backoff_seconds: float = 0.1  # 重试退避基础秒数（实际睡眠 = backoff * (attempt+1)）
    pool_min: int = 1             # 连接池最小连接数
    pool_max: int = 10            # 连接池最大连接数

    # psycopg2 连接参数（传递给 connect() 的额外 kwargs）
    connect_kwargs: dict = field(default_factory=dict)

    @staticmethod
    def from_env(prefix: str = "DB_") -> "DbConfig":
        """从环境变量读取配置。

        环境变量：
          {prefix}CONNECTION  — 完整连接字符串（优先级最高）
          {prefix}HOST        — 主机名
          {prefix}PORT        — 端口
          {prefix}NAME        — 数据库名
          {prefix}USER        — 用户名
          {prefix}PASSWORD    — 密码
          {prefix}RETRY       — 重试次数
          {prefix}BACKOFF     — 退避基础秒数
        """
        conn_str = os.environ.get(f"{prefix}CONNECTION", "")
        if conn_str:
            return DbConfig(
                connection_string=conn_str,
                retry_count=int(os.environ.get(f"{prefix}RETRY", "3")),
                backoff_seconds=float(os.environ.get(f"{prefix}BACKOFF", "0.1")),
            )

        return DbConfig(
            host=os.environ.get(f"{prefix}HOST", ""),
            port=int(os.environ.get(f"{prefix}PORT", "5432")),
            dbname=os.environ.get(f"{prefix}NAME", ""),
            user=os.environ.get(f"{prefix}USER", ""),
            password=os.environ.get(f"{prefix}PASSWORD", ""),
            retry_count=int(os.environ.get(f"{prefix}RETRY", "3")),
            backoff_seconds=float(os.environ.get(f"{prefix}BACKOFF", "0.1")),
        )

    def get_connection_string(self) -> str:
        """获取连接字符串。"""
        if self.connection_string:
            return self.connection_string
        auth = f"{self.user}:{self.password}" if self.password else self.user
        host = self.host or "localhost"
        return f"postgresql://{auth}@{host}:{self.port}/{self.dbname}"
