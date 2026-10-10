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
    """数据库连接配置。

    用法：
      # 方式一：完整连接字符串
      cfg = DbConfig(connection_string="postgresql://user:pass@host:5432/dbname")

      # 方式二：从环境变量自动组装
      cfg = DbConfig.from_env()

      # 方式三：显式参数
      cfg = DbConfig(host="localhost", port=5432, dbname="mydb", user="pg", password="secret")
    """

    connection_string: str = ""
    host: str = "localhost"
    port: int = 5432
    dbname: str = ""
    user: str = ""
    password: str = ""

    # psycopg2 连接参数（传递给 connect() 的额外 kwargs）
    connect_kwargs: dict = field(default_factory=dict)

    @staticmethod
    def from_env(prefix: str = "DB_") -> "DbConfig":
        """从环境变量读取配置。

        环境变量：
          {prefix}CONNECTION  — 完整连接字符串（优先级最高）
          {prefix}HOST        — 主机名（默认 localhost）
          {prefix}PORT        — 端口（默认 5432）
          {prefix}NAME        — 数据库名
          {prefix}USER        — 用户名
          {prefix}PASSWORD    — 密码
        """
        conn_str = os.environ.get(f"{prefix}CONNECTION", "")
        if conn_str:
            return DbConfig(connection_string=conn_str)

        return DbConfig(
            host=os.environ.get(f"{prefix}HOST", "localhost"),
            port=int(os.environ.get(f"{prefix}PORT", "5432")),
            dbname=os.environ.get(f"{prefix}NAME", ""),
            user=os.environ.get(f"{prefix}USER", ""),
            password=os.environ.get(f"{prefix}PASSWORD", ""),
        )

    def get_connection_string(self) -> str:
        """获取连接字符串。"""
        if self.connection_string:
            return self.connection_string
        auth = f"{self.user}:{self.password}" if self.password else self.user
        return f"postgresql://{auth}@{self.host}:{self.port}/{self.dbname}"
