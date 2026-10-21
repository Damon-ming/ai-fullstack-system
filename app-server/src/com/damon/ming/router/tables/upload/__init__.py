# router/tables/upload/__init__.py
"""
上传文件审计表 —— 对外暴露表对象、create_upload_tables()。
"""

from src.com.damon.ming.router.tables.upload.tables import (
    create_upload_tables,
    upload_records,
)

__all__ = ["create_upload_tables", "upload_records"]
