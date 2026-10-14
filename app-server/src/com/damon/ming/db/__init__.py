# app-server/src/com/damon/ming/db/__init__.py
"""
数据库连接层 —— 纯技术模块，零业务逻辑，可独立移植。

通用多数据库支持（PostgreSQL / MySQL / SQLite 等），后端无关的设计：
  - 通过 SQLAlchemy 引擎自动识别驱动，无需修改代码即可切换数据库
  - 原生 SQL 通过 text() 执行，保留各数据库特有语法（如 pgvector 的 <=>、::vector）
  - 连接池由 SQLAlchemy 内置 QueuePool 管理，线程安全

独立的，没有业务的。可被项目中任何需要数据库访问的模块引用。
上层通过 app 里的 YAML 配置（db-config.yaml）进行配置，本模块不感知配置来源。

提供：
  - DbConfig:       数据库连接配置（纯数据类，支持多后端 URL 格式）
  - DbConnection:   连接管理（SQLAlchemy 引擎 + 连接池 + 自动重连）
  - query / execute: 底层 SQL 执行工具

不提供（它们属于业务层 app/）：
  - 配置加载 → 见 app/config/db_config_loader.py
  - 表结构迁移 → 暂无（后续独立模块）

用法：
  from src.com.damon.ming.db import DbConfig, DbConnection, query, execute

  # PostgreSQL
  db = DbConnection(DbConfig(url="postgresql://user:pass@localhost/mydb"))
  db.initialize()
  rows = query("SELECT * FROM users WHERE id = %s", (user_id,))

  # MySQL
  db = DbConnection(DbConfig(url="mysql+pymysql://user:pass@localhost/mydb"))
  db.initialize()

  # SQLite
  db = DbConnection(DbConfig(url="sqlite:///path/to/db.sqlite"))
  db.initialize()
"""

from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.db.db_connection import DbConnection, execute, query

__all__ = [
    "DbConfig",
    "DbConnection",
    "execute",
    "query",
]
