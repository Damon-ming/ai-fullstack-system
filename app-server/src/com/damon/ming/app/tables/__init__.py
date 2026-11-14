# app-server/src/com/damon/ming/app/tables/__init__.py
"""
表定义聚合入口 —— 各业务模块的表定义汇总。

结构：
  base.py           共享 MetaData 实例 + _NOW
  account_tables.py    账号体系表（users / devices / sessions）
  encryption_tables.py 加密体系表（encryption_sessions）
  history_tables.py    对话历史表（history_conversations / history_turns）
  upload_tables.py     上传记录表（upload_records）
  __init__.py       聚合调用各模块的 create_X_tables()

使用方式：
  from src.com.damon.ming.app.tables import create_all_tables, metadata
  create_all_tables(db_conn)
"""

from src.com.damon.ming.app.tables.account_tables import create_account_tables
from src.com.damon.ming.app.tables.encryption_tables import create_encryption_tables
from src.com.damon.ming.app.tables.history_tables import create_history_tables
from src.com.damon.ming.app.tables.upload_tables import create_upload_tables


def create_all_tables(db_conn) -> None:
    """创建所有模块的表 + 索引（幂等）。

    按模块依次调用各自的 create_X_tables()，
    每个模块负责自己的 metadata.create_all() + 索引 DDL。
    """
    create_account_tables(db_conn)
    create_encryption_tables(db_conn)
    create_history_tables(db_conn)
    create_upload_tables(db_conn)
