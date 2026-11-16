"""上传记录查询。"""

from sqlalchemy import select
from src.com.damon.ming.app.tables.account_tables import users
from src.com.damon.ming.app.tables.upload_tables import upload_records
from src.com.damon.ming.db import get_default_db


def get_file_uploader_map() -> dict[str, str]:
    """查询文件上传者昵称，返回 ``{file_path: uploader_name}``。"""
    try:
        with get_default_db().engine.connect() as conn:
            rows = conn.execute(
                select(upload_records.c.file_path, users.c.name).select_from(
                    upload_records.outerjoin(
                        users, upload_records.c.user_id == users.c.user_id
                    )
                )
            ).fetchall()
        return {row[0]: (row[1] or "") for row in rows}
    except Exception:
        return {}
