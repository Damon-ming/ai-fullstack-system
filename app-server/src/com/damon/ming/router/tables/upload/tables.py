# router/tables/upload/tables.py
"""
上传文件审计表 —— upload_records。

每条记录对应一次文件上传事件（file_uid 维度），
用于审计追溯（谁、何时、哪台设备上传了什么）。
向量库按 file_sha256 去重，审计表按 file_uid 记录每次上传。
"""

from sqlalchemy import Column, String, Table
from src.com.damon.ming.router.tables.base import metadata

# ---------------------------------------------------------------------------
# upload_records 表
# ---------------------------------------------------------------------------

upload_records = Table(
    "upload_records",
    metadata,
    Column("file_uid", String(64), primary_key=True),
    Column("file_sha256", String(64), nullable=False),
    Column("file_path", String(512), nullable=False),
    Column("file_size", String(20), nullable=False, default="0"),
    Column("token", String(64), nullable=True),
    Column("device_id", String(64), nullable=False, server_default=""),
)

_UPLOAD_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_upload_sha ON upload_records (file_sha256)",
    "CREATE INDEX IF NOT EXISTS idx_upload_token ON upload_records (token)",
]


def create_upload_tables(db_conn) -> None:
    """创建上传审计表 + 索引（幂等）。"""
    metadata.create_all(db_conn.engine)
    for ddl in _UPLOAD_INDEX_DDL:
        db_conn.execute(ddl, commit=True)
