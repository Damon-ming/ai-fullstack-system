# app-server/src/com/damon/ming/router/tables/__init__.py
"""
表定义聚合入口 —— 各 router 模块的表定义汇总。

结构：
  base.py           共享 MetaData 实例 + _NOW
  account/          账号体系表（users / devices / sessions）
  encryption/       加密体系表（encryption_sessions）
  history/          对话历史表（history_conversations）
  __init__.py       聚合调用各模块的 create_X_tables()

使用方式：
  from src.com.damon.ming.router.tables import create_all_tables, metadata
  create_all_tables(db_conn)
"""

from src.com.damon.ming.router.tables.account import create_account_tables
from src.com.damon.ming.router.tables.base import metadata
from src.com.damon.ming.router.tables.encryption import create_encryption_tables
from src.com.damon.ming.router.tables.history import create_history_tables
from src.com.damon.ming.router.tables.upload import create_upload_tables


def create_all_tables(db_conn) -> None:
    """创建所有模块的表 + 索引（幂等）。

    按模块依次调用各自的 create_X_tables()，
    每个模块负责自己的 metadata.create_all() + 索引 DDL。
    """
    create_account_tables(db_conn)
    create_encryption_tables(db_conn)
    create_history_tables(db_conn)
    create_upload_tables(db_conn)
