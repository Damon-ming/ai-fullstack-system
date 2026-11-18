# app-server/src/com/damon/ming/router/upload/service/upload_service.py
import asyncio
from pathlib import Path

from fastapi import UploadFile
from src.com.damon.ming.ai.knowledge.index_service import KnowledgeIndexService
from src.com.damon.ming.app.thread_pools import get_database_query_pool, run_in_pool
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.upload.service.file_validator import (
    validate_upload_content,
)
from src.com.damon.ming.router.upload.service.upload_audit_repository import (
    create_upload_records,
    update_upload_record,
)
from src.com.damon.ming.router.upload.service.upload_file_storage import (
    UploadFileStorage,
)
from src.com.damon.ming.security.digest import sha256_hex
from src.com.damon.ming.utils.time import now_iso
from src.com.damon.ming.utils.uuid import generate_uuid_hex

logger = pin("upload.service")
MIB = 1024 * 1024


class UploadService:
    """编排批量上传、向量入库、审计记录和失败回滚。"""

    @staticmethod
    async def batch_save_files(
        file_list: list[UploadFile],
        upload_config,
        knowledge_index: KnowledgeIndexService,
        executor=None,
        user_id: int | None = None,
        device_id: str = "",
    ) -> dict:
        success_files: list[dict] = []
        duplicate_files: list[dict] = []
        failed_files: list[dict] = []
        allowed_exts = sorted(upload_config.allowed_types.keys())

        # 先为本批文件建立审计记录。审计表不可用时，不开始写磁盘或 vector_db。
        contexts = []
        audit_rows = []
        for file in file_list:
            file_name = Path(file.filename or "unnamed").name
            file_id = generate_uuid_hex()
            file_size = getattr(file, "size", None)
            contexts.append(
                {
                    "file": file,
                    "filename": file_name,
                    "file_id": file_id,
                    "file_size": file_size,
                    "suffix": Path(file_name).suffix.lower(),
                }
            )
            audit_rows.append(
                {
                    "file_id": file_id,
                    "file_name": file_name,
                    "file_size": str(file_size or 0),
                    "user_id": user_id,
                    "device_id": device_id[:64] if device_id else "",
                    "status": "processing",
                }
            )
        await run_in_pool(get_database_query_pool(), create_upload_records, audit_rows)

        if len(file_list) > upload_config.max_files_per_request:
            message = t(
                I18nKey.UPLOAD_TOO_MANY_FILES,
                max_files=str(upload_config.max_files_per_request),
                actual=str(len(file_list)),
            )
            await _finish_many(contexts, "rejected", "request_validation", message)
            raise ValueError(message)

        file_sizes = [ctx["file_size"] for ctx in contexts]
        if any(size is None for size in file_sizes):
            message = "无法确认上传文件总大小"
            await _finish_many(contexts, "rejected", "request_validation", message)
            raise ValueError(message)

        total_size = sum(file_sizes)
        if total_size > upload_config.max_total_upload_size:
            message = t(
                I18nKey.UPLOAD_TOTAL_SIZE_EXCEEDED,
                max_mb=str(upload_config.max_total_upload_size // MIB),
            )
            await _finish_many(contexts, "rejected", "request_validation", message)
            raise ValueError(message)

        for ctx in contexts:
            file = ctx["file"]
            file_name = ctx["filename"]
            file_id = ctx["file_id"]
            file_size = ctx["file_size"]
            suffix = ctx["suffix"]
            file_sha256 = ""
            file_path: Path | None = None
            ingest_started = False
            vector_written = False
            repaired_old_path: str | None = None
            path_repair_attempted = False

            try:
                if not upload_config.is_type_allowed(suffix):
                    message = t(
                        I18nKey.UPLOAD_TYPE_REJECTED,
                        suffix=suffix or t(I18nKey.UPLOAD_NO_EXTENSION),
                        allowed=", ".join(allowed_exts),
                    )
                    await _finish_audit(file_id, "rejected", "type_validation", message)
                    failed_files.append(
                        {
                            "filename": file_name,
                            "file_size": file_size or 0,
                            "file_sha256": "",
                            "error": message,
                        }
                    )
                    continue

                max_size = upload_config.get_max_size_for_ext(suffix)
                if file_size > max_size:
                    message = t(
                        I18nKey.UPLOAD_SIZE_EXCEEDED,
                        max_mb=str(max_size // MIB),
                    )
                    await _finish_audit(file_id, "rejected", "size_validation", message)
                    failed_files.append(
                        {
                            "filename": file_name,
                            "file_size": file_size,
                            "file_sha256": "",
                            "error": message,
                        }
                    )
                    continue

                chunks: list[bytes] = []
                while True:
                    chunk = await file.read(MIB)
                    if not chunk:
                        break
                    chunks.append(chunk)
                content = b"".join(chunks)

                try:
                    validate_upload_content(suffix, content)
                except ValueError:
                    message = t(I18nKey.UPLOAD_CONTENT_INVALID)
                    await _finish_audit(
                        file_id, "rejected", "content_validation", message
                    )
                    failed_files.append(
                        {
                            "filename": file_name,
                            "file_size": file_size,
                            "file_sha256": "",
                            "error": message,
                        }
                    )
                    continue

                file_sha256 = sha256_hex(content)
                file_path = UploadFileStorage.build_file_path(
                    file_id,
                    file_name,
                    suffix,
                )
                resolved_path = str(file_path.resolve())
                await _update_audit(
                    file_id,
                    file_sha256=file_sha256,
                    file_path=resolved_path,
                )

                logger.info(
                    "收到用户上传文件 | user_id=%s | device=%s | filename=%s | size=%s | type=%s",
                    user_id if user_id is not None else "anon",
                    device_id[:8] if device_id else "-",
                    repr(file_name),
                    len(content),
                    suffix,
                )

                await UploadFileStorage.store_content(file_path, content, executor)

                ingest_started = True
                index_result = await knowledge_index.ingest_files(
                    [resolved_path],
                    file_id=file_id,
                    disk_file_at=now_iso(),
                    file_name=file_name,
                )
                indexed_shas = {item["file_sha256"] for item in index_result["indexed"]}
                skipped_items = [
                    item
                    for item in index_result["skipped"]
                    if item.get("file_sha256") == file_sha256
                ]

                if file_sha256 in indexed_shas:
                    vector_written = True
                    await _finish_audit(
                        file_id,
                        "indexed",
                        file_sha256=file_sha256,
                        file_path=resolved_path,
                    )
                    success_files.append({"filename": file_name, "file_id": file_id})
                    continue

                if skipped_items:
                    skipped = skipped_items[0]
                    existing_path = skipped.get("existing_file_path")
                    stored_path = skipped.get("stored_file_path")
                    if existing_path and Path(existing_path).is_file():
                        if not UploadFileStorage.remove_file(
                            file_path
                        ) and not UploadFileStorage.move_to_temporary(file_path):
                            raise OSError("无法清理重复上传的磁盘文件")
                        audit_path = existing_path
                    else:
                        # 同 SHA 的向量仍在，但原文件路径已失效；复用现有向量并修复来源路径。
                        repaired_old_path = stored_path
                        path_repair_attempted = True
                        repaired = await run_in_pool(
                            get_database_query_pool(),
                            knowledge_index.update_file_path_by_sha,
                            file_sha256,
                            resolved_path,
                        )
                        if repaired == 0:
                            raise RuntimeError("未找到可修复路径的向量记录")
                        audit_path = resolved_path

                    await _finish_audit(
                        file_id,
                        "duplicate",
                        file_sha256=file_sha256,
                        file_path=audit_path,
                    )
                    duplicate_files.append({"filename": file_name})
                    continue

                # 文件解析失败，返回结果里既没有 indexed 项，也没有对应 SHA 的 skipped 项，让外层执行失败处理和磁盘回滚
                raise RuntimeError(t(I18nKey.UPLOAD_VECTOR_DB_ERROR))

            except asyncio.CancelledError:
                if path_repair_attempted:
                    rollback_ok = await _restore_duplicate_path(
                        knowledge_index, file_sha256, repaired_old_path, file_path
                    )
                else:
                    rollback_ok = _rollback_file(
                        file_path,
                        file_id,
                        knowledge_index if ingest_started else None,
                        delete_vectors=ingest_started,
                    )
                if rollback_ok:
                    await _finish_audit_after_cancel(
                        file_id, "cancelled", "request_cancelled"
                    )
                else:
                    logger.error(
                        "取消上传补偿未完成，保留 processing 审计状态 | id=%s",
                        file_id[:16],
                    )
                raise

            except Exception as exc:
                audit_write_failed = isinstance(exc, AuditUpdateFailure)
                if path_repair_attempted:
                    rollback_ok = await _restore_duplicate_path(
                        knowledge_index, file_sha256, repaired_old_path, file_path
                    )
                else:
                    should_delete_vectors = vector_written
                    rollback_ok = _rollback_file(
                        file_path,
                        file_id,
                        knowledge_index if should_delete_vectors else None,
                        delete_vectors=should_delete_vectors,
                    )
                    if not rollback_ok:
                        logger.error(
                            "上传补偿未完全完成 | file_id=%s | filename=%s",
                            file_id[:16],
                            file_name,
                        )

                logger.warning(
                    "文件上传失败并执行补偿 | filename=%s | sha=%s | error=%s",
                    file_name,
                    file_sha256[:16],
                    exc,
                )
                if rollback_ok and not audit_write_failed:
                    try:
                        await _finish_audit(
                            file_id,
                            "failed",
                            "upload",
                            str(exc),
                        )
                    except Exception:
                        # 保留 processing，表示终态审计未能落库，便于结合日志排查。
                        logger.exception(
                            "上传回滚完成但终态审计写入失败，保留 processing 状态 | id=%s",
                            file_id[:16],
                        )
                elif not rollback_ok:
                    logger.error(
                        "回滚未完成，保留 processing 审计状态 | id=%s",
                        file_id[:16],
                    )
                failed_files.append(
                    {
                        "filename": file_name,
                        "file_size": file_size or 0,
                        "file_sha256": file_sha256,
                        "error": str(exc),
                    }
                )

        logger.info(
            "批量上传完成 | 总计=%d | 成功=%d | 重复=%d | 失败=%d",
            len(file_list),
            len(success_files),
            len(duplicate_files),
            len(failed_files),
        )
        return {
            "success_files": success_files,
            "duplicate_files": duplicate_files,
            "failed_files": failed_files,
        }


class AuditUpdateFailure(RuntimeError):
    """审计状态写入失败，上传数据需要补偿回滚。"""


async def _update_audit(file_id: str, **kwargs) -> None:
    try:
        await run_in_pool(
            get_database_query_pool(), update_upload_record, file_id, **kwargs
        )
    except Exception as exc:
        raise AuditUpdateFailure("写入上传审计状态失败") from exc


async def _finish_audit(
    file_id: str,
    status: str,
    error_stage: str | None = None,
    error_msg: str | None = None,
    *,
    file_sha256: str | None = None,
    file_path: str | None = None,
) -> None:
    try:
        await run_in_pool(
            get_database_query_pool(),
            update_upload_record,
            file_id,
            status=status,
            file_sha256=file_sha256,
            file_path=file_path,
            error_stage=error_stage,
            error_msg=error_msg,
            finished=True,
        )
    except Exception as exc:
        raise AuditUpdateFailure("写入上传审计终态失败") from exc


async def _finish_many(
    contexts: list[dict], status: str, error_stage: str, error_msg: str
) -> None:
    for ctx in contexts:
        await _finish_audit(ctx["file_id"], status, error_stage, error_msg)


async def _finish_audit_after_cancel(
    file_id: str, error_msg: str, error_stage: str
) -> None:
    try:
        await asyncio.shield(_finish_audit(file_id, "failed", error_stage, error_msg))
    except Exception:
        logger.exception("取消上传后更新审计状态失败 | file_id=%s", file_id[:16])


async def _restore_duplicate_path(
    knowledge_index: KnowledgeIndexService,
    file_sha256: str,
    old_path: str | None,
    new_file_path: Path | None,
) -> bool:
    try:
        updated = await run_in_pool(
            get_database_query_pool(),
            knowledge_index.update_file_path_by_sha,
            file_sha256,
            old_path,
        )
        if updated == 0:
            raise RuntimeError("恢复重复文件原路径时未匹配到向量记录")
    except Exception:
        logger.exception("恢复重复文件原路径失败 | sha=%s", file_sha256[:16])
        return False
    if new_file_path is None or UploadFileStorage.remove_file(new_file_path):
        return True
    return UploadFileStorage.move_to_temporary(new_file_path)


def _rollback_file(
    file_path: Path | None,
    file_id: str,
    knowledge_index: KnowledgeIndexService | None,
    *,
    delete_vectors: bool,
) -> bool:
    """回滚本次上传；仅在结果可能已提交时删除向量记录。"""
    if delete_vectors and knowledge_index:
        try:
            deleted = knowledge_index.delete_by_id(file_id)
            logger.info("补偿删除向量记录 | id=%s | deleted=%d", file_id[:16], deleted)
        except Exception:
            logger.exception("补偿删除向量记录失败，保留源文件 | id=%s", file_id[:16])
            return False

    if file_path is None or UploadFileStorage.remove_file(file_path):
        return True
    return UploadFileStorage.move_to_temporary(file_path)
