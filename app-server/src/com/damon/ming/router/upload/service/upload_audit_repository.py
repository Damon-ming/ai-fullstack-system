# app-server/src/com/damon/ming/router/upload/service/upload_audit_repository.py
"""上传操作审计记录持久化。"""

from datetime import UTC, datetime

from sqlalchemy import select, update
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
                select(upload_records.c.file_path, users.c.name)
                .select_from(
                    upload_records.outerjoin(
                        users, upload_records.c.user_id == users.c.user_id
                    )
                )
                .where(upload_records.c.status == "indexed")
            ).fetchall()
        return {row[0]: (row[1] or "") for row in rows if row[0]}
    except Exception:
        return {}


def create_upload_records(records: list[dict]) -> None:
    """批量创建 processing 审计记录；整批失败时不应开始文件写入。"""
    if not records:
        return
    try:
        get_default_db().execute(
            pg_insert(upload_records)
            .values(records)
            .on_conflict_do_nothing(index_elements=[upload_records.c.file_uid]),
            commit=True,
        )
    except Exception as exc:
        logger.error("创建上传审计记录失败 | count=%d | error=%s", len(records), exc)
        raise


def update_upload_record(
    file_uid: str,
    *,
    status: str | None = None,
    file_sha256: str | None = None,
    file_path: str | None = None,
    error_stage: str | None = None,
    error_msg: str | None = None,
    finished: bool = False,
) -> None:
    """更新上传审计状态；finished=True 表示本次操作已到终态。"""
    values: dict = {}
    if status is not None:
        values["status"] = status
    if file_sha256 is not None:
        values["file_sha256"] = file_sha256
    if file_path is not None:
        values["file_path"] = file_path
    if error_stage is not None:
        values["error_stage"] = error_stage
    if error_msg is not None:
        values["error_msg"] = error_msg[:4000]
    if finished:
        values["completed_at"] = datetime.now(tz=UTC)
    if not values:
        return

    try:
        result = get_default_db().execute(
            update(upload_records)
            .where(upload_records.c.file_uid == file_uid)
            .values(**values),
            commit=True,
        )
        if result == 0:
            raise RuntimeError(f"上传审计记录不存在 | file_uid={file_uid}")
    except Exception as exc:
        logger.error(
            "更新上传审计记录失败 | file_uid=%s | status=%s | error=%s",
            file_uid[:16],
            status,
            exc,
        )
        raise


def get_processing_upload_records() -> list[dict] | None:
    """读取未到终态的上传记录；查询失败返回 None，禁止据此清理磁盘文件。"""
    try:
        with get_default_db().engine.connect() as conn:
            rows = conn.execute(
                select(
                    upload_records.c.file_uid,
                    upload_records.c.file_sha256,
                    upload_records.c.file_path,
                ).where(upload_records.c.status == "processing")
            ).fetchall()
        return [
            {"file_uid": row[0], "file_sha256": row[1], "file_path": row[2]}
            for row in rows
        ]
    except Exception as exc:
        logger.error("查询未完成上传审计记录失败 | error=%s", exc)
        return None
