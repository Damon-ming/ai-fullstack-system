# app-server/src/com/damon/ming/router/account/account_schema.py
"""
账号体系数据库模式 —— 建表执行函数。

包含 3 张业务表（v1 直接建表，无迁移追踪）：
  - users:    用户身份（phone → token）
  - devices:  设备指纹（独立于用户存在）
  - sessions: 会话实例（token + device 的唯一组合）

DDL 定义在 sql/ 子目录各表对应文件，本文件只负责执行。
"""

from src.com.damon.ming.db.db_connection import DbConnection
from src.com.damon.ming.router.account.sql.devices_sql import DDL as DDL_DEVICES
from src.com.damon.ming.router.account.sql.sessions_sql import DDL as DDL_SESSIONS
from src.com.damon.ming.router.account.sql.users_sql import DDL as DDL_USERS


def create_account_tables(db_conn: DbConnection) -> None:
    """创建账号体系所有表 + 索引（幂等）。

    用法：
        db_conn = DbConnection(config)
        db_conn.initialize()
        create_account_tables(db_conn)
    """
    db_conn.execute(DDL_USERS, commit=True)
    db_conn.execute(DDL_DEVICES, commit=True)
    db_conn.execute(DDL_SESSIONS, commit=True)
