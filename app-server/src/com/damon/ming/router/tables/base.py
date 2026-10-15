# app-server/src/com/damon/ming/router/tables/base.py
"""
表定义共享基础设施 —— 单一 MetaData 实例 + 共享 server_default。

所有 router 模块的 tables.py 必须从这里导入 metadata 和 _NOW，
确保所有表注册到同一个 MetaData 实例，create_all() 才能一次建完全部表。
"""

from sqlalchemy import MetaData, text

# 全局共享 MetaData —— 所有表注册于此
metadata = MetaData()

# 共享 server_default
_NOW = text("NOW()")
