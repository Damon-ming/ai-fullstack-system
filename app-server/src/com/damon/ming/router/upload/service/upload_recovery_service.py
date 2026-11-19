"""启动时恢复未完成的上传操作。

本模块负责协调上传审计记录、磁盘文件和 vector DB 状态，收尾进程中断后
遗留的 processing 上传：确认已入库的记录并补全审计状态；对确认未入库的
上传文件执行清理并记录失败；处理重复上传留下的文件和路径。

知识库扫描及 vector DB 启动补录由 ``knowledge_bootstrap`` 负责。本模块消费
其补录结果并结合上传审计记录决定如何恢复，不负责通用知识文件的索引构建。
"""

from pathlib import Path

from src.com.damon.ming.ai.rag.knowledge.index_service import KnowledgeIndexService
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.upload.service.upload_audit_repository import (
    get_processing_upload_records,
    update_upload_record,
)
from src.com.damon.ming.router.upload.service.upload_file_storage import (
    UploadFileStorage,
)

logger = pin("upload.recovery")


class UploadRecoveryService:
    """协调上传审计记录、磁盘文件与启动索引结果。"""

    @staticmethod
    def recover_startup(knowledge_index: KnowledgeIndexService) -> None:
        pending_records = get_processing_upload_records()
        if pending_records is None:
            raise RuntimeError("无法读取未完成上传审计记录，启动恢复中止")

        if not pending_records and not knowledge_index.startup_index_failures:
            return

        removed_paths: set[str] = set()
        resolved_ids: set[str] = set()
        for failure in knowledge_index.startup_index_failures:
            file_sha = failure.file_sha256
            current_shas = knowledge_index.get_indexed_file_shas()
            if current_shas is None:
                raise RuntimeError(
                    "启动补录失败且无法确认 vector_db 状态，保留磁盘文件"
                )

            matching = _matching_pending_records(
                pending_records, file_sha, set(failure.file_paths)
            )
            if file_sha in current_shas:
                # 写入异常可能发生在 commit 返回之后；以数据库查询结果为准。
                for record in matching:
                    update_upload_record(
                        record["file_id"],
                        status="indexed",
                        file_sha256=file_sha,
                        file_path=record["file_path"],
                        finished=True,
                    )
                    resolved_ids.add(record["file_id"])
                continue

            if not matching:
                raise RuntimeError(
                    f"非上传来源的知识文件补录失败 | sha={file_sha[:16]} | "
                    f"error={failure.error}"
                )

            matching_paths = {
                str(Path(record["file_path"]).resolve())
                for record in matching
                if record["file_path"]
            }
            failure_paths = {str(Path(path).resolve()) for path in failure.file_paths}
            if matching_paths != failure_paths:
                raise RuntimeError(
                    f"同 SHA 还包含非未完成上传来源，保留磁盘文件 | sha={file_sha[:16]}"
                )

            for record in matching:
                file_path = Path(record["file_path"])
                if not _discard_file(file_path):
                    raise RuntimeError(f"启动恢复时无法清理孤立文件: {file_path}")
                removed_paths.add(str(file_path.resolve()))
                update_upload_record(
                    record["file_id"],
                    status="failed",
                    error_stage="startup_recovery",
                    error_msg=f"启动增量入库失败，已清理磁盘文件: {failure.error}",
                    finished=True,
                )
                resolved_ids.add(record["file_id"])
                logger.error(
                    "启动补录失败，清理未完成上传文件 | id=%s | path=%s | error=%s",
                    record["file_id"][:16],
                    file_path,
                    failure.error,
                )

        # 处理“向量已提交、审计终态未提交”以及重复上传的中断状态。
        current_shas = knowledge_index.get_indexed_file_shas()
        if current_shas is None:
            raise RuntimeError("无法确认 vector_db 状态，保留未完成上传")
        for record in pending_records:
            if record["file_id"] in resolved_ids:
                continue
            file_sha = record["file_sha256"]
            raw_path = record["file_path"]
            if not file_sha or file_sha not in current_shas:
                continue

            file_path = Path(raw_path) if raw_path else None
            if file_path is None or not file_path.is_file():
                continue

            stored_paths = [
                Path(path).resolve()
                for path in knowledge_index.get_indexed_file_paths_by_sha(file_sha)
            ]
            current_file_path = file_path.resolve()
            existing_path = next(
                (path for path in stored_paths if path.is_file()),
                None,
            )

            if existing_path and existing_path != current_file_path:
                if not _discard_file(file_path):
                    raise RuntimeError(f"无法清理中断的重复上传文件: {file_path}")
                removed_paths.add(str(current_file_path))
                status = "duplicate"
                audit_path = str(existing_path)
            else:
                if not existing_path:
                    knowledge_index.update_file_path_by_sha(
                        file_sha, str(current_file_path)
                    )
                status = "indexed"
                audit_path = str(current_file_path)

            update_upload_record(
                record["file_id"],
                status=status,
                file_sha256=file_sha,
                file_path=audit_path,
                finished=True,
            )
            resolved_ids.add(record["file_id"])

        # 已落盘但未能被任何数据源解析的 processing 文件也无法补录。
        current_shas = knowledge_index.get_indexed_file_shas()
        if current_shas is None:
            raise RuntimeError("无法确认 vector_db 状态，保留未解析上传文件")
        discovered_paths = knowledge_index.startup_discovered_file_paths
        for record in pending_records:
            if record["file_id"] in resolved_ids:
                continue
            file_sha = record["file_sha256"]
            raw_path = record["file_path"]
            if not raw_path or not file_sha:
                continue
            file_path = Path(raw_path)
            resolved_path = str(file_path.resolve())
            if not file_path.is_file() or resolved_path in discovered_paths:
                continue
            if file_sha in current_shas:
                continue
            if not _discard_file(file_path):
                raise RuntimeError(f"启动恢复时无法清理未解析文件: {file_path}")
            removed_paths.add(resolved_path)
            update_upload_record(
                record["file_id"],
                status="failed",
                error_stage="startup_recovery",
                error_msg="启动扫描未能解析该文件，已清理磁盘文件",
                finished=True,
            )
            logger.error(
                "启动恢复：上传文件未被知识源解析，已清理 | id=%s | path=%s",
                record["file_id"][:16],
                file_path,
            )

        if removed_paths:
            knowledge_index.remove_source_paths(removed_paths)


def _matching_pending_records(
    records: list[dict], file_sha: str, file_paths: set[str]
) -> list[dict]:
    normalized_paths = {str(Path(path).resolve()) for path in file_paths}
    return [
        record
        for record in records
        if record["file_sha256"] == file_sha
        and record["file_path"]
        and str(Path(record["file_path"]).resolve()) in normalized_paths
    ]


def _discard_file(file_path: Path) -> bool:
    if UploadFileStorage.remove_file(file_path):
        return True
    if not UploadFileStorage.move_to_temporary(file_path):
        return False
    temporary_path = file_path.with_suffix(file_path.suffix + ".tmp")
    return UploadFileStorage.remove_file(temporary_path)
