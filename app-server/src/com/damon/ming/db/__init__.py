# app-server/src/com/damon/ming/db/__init__.py
"""
数据库连接层 —— 纯技术模块，零业务逻辑，可独立移植。

提供：
  - DbConfig:       数据库连接配置
  - DbConnection:   连接管理（连接池 + 自动重连）
  - DbMigration:    表结构迁移（建表、建索引、版本追踪）
  - query / execute: 底层 SQL 执行工具

设计原则：
  - 不依赖任何业务模块（encryption、router、middleware 等）
  - 可被项目中任何需要数据库访问的模块引用
  - 后端当前使用 psycopg2 + PostgreSQL，抽象接口便于切换驱动

用法：
  from src.com.damon.ming.db import DbConfig, DbConnection, query, execute

  db = DbConnection(DbConfig(connection_string="postgresql://..."))
  db.initialize()  # 测试连接

  rows = query("SELECT * FROM sessions WHERE key_id = %s", (key_id,))
  execute("INSERT INTO sessions (...) VALUES (...)", params)
  db.migrate("001_create_sessions", ddl_sql)
"""

from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.db.db_config_loader import DbConfigLoader
from src.com.damon.ming.db.db_connection import DbConnection, execute, query
from src.com.damon.ming.db.db_migration import DbMigration

__all__ = [
    "DbConfig",
    "DbConfigLoader",
    "DbConnection",
    "DbMigration",
    "execute",
    "query",
]
