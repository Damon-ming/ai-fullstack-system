"""上传记录持久化操作。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.com.damon.ming.app.tables.account_tables import users
from src.com.damon.ming.app.tables.upload_tables import upload_records
from src.com.damon.ming.db import get_default_db
from src.com.damon.ming.log import pin

logger = pin("upload.store")


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


def record_upload_metadata(
    file_uid: str,
    file_sha256: str,
    file_path: str,
    file_size: int,
    user_id: int | None,
    device_id: str,
) -> None:
    """写入上传审计记录；失败只记日志，不影响上传结果。"""
    try:
        get_default_db().execute(
            pg_insert(upload_records)
            .values(
                file_uid=file_uid,
                file_sha256=file_sha256,
                file_path=file_path,
                file_size=str(file_size),
                user_id=user_id,
                device_id=device_id[:64] if device_id else "",
                created_at=datetime.now(tz=UTC),
            )
            .on_conflict_do_nothing(index_elements=[upload_records.c.file_uid]),
            commit=True,
        )
    except Exception as e:
        logger.error(
            "写入审计表失败 | file_uid=%s sha=%s error=%s",
            file_uid[:16],
            file_sha256[:16],
            e,
        )
