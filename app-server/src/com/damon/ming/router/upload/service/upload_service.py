# app-server/src/com/damon/ming/upload/service/upload_service.py
import asyncio
from pathlib import Path

from fastapi import UploadFile
from src.com.damon.ming.ai.rag_tool import RAGContainer
from src.com.damon.ming.app.thread_pools import get_database_query_pool, run_in_pool
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.upload.service.file_validator import (
    validate_upload_content,
)
from src.com.damon.ming.router.upload.service.upload_file_store import UploadFileStore
from src.com.damon.ming.router.upload.service.upload_store import (
    record_upload_metadata,
)
from src.com.damon.ming.security.digest import sha256_hex
from src.com.damon.ming.thread import CancellationToken
from src.com.damon.ming.utils.time import now_iso
from src.com.damon.ming.utils.uuid import generate_uuid_hex

logger = pin("upload.service")
MIB = 1024 * 1024


class UploadService:
    """编排批量上传、向量入库和失败回滚。"""

    @staticmethod
    async def batch_save_files(
        file_list: list[UploadFile],
        upload_config,
        rag_app: RAGContainer,
        cancellation_token: CancellationToken | None = None,
        executor=None,
        user_id: int | None = None,
        device_id: str = "",
    ) -> dict:
        """批量保存文件——每个文件独立原子提交。

        逐文件处理，每个文件走完整生命周期：
          1. 校验类型/大小
          2. 原子写入磁盘
          3. 逐文件入库向量库
          4. 任一步失败 → 回滚该文件的磁盘和向量索引，继续处理下一个

        每个文件互不影响，一个失败不会中断其他文件。

        Returns:
            {"files": [成功文件meta...], "failed_files": [失败文件信息...]}
        """
        success_files: list[dict] = []
        duplicate_files: list[dict] = []
        failed_files: list[dict] = []
        allowed_exts = sorted(upload_config.allowed_types.keys())

        # 文件数量校验
        if len(file_list) > upload_config.max_files_per_request:
            raise ValueError(
                t(
                    I18nKey.UPLOAD_TOO_MANY_FILES,
                    max_files=str(upload_config.max_files_per_request),
                    actual=str(len(file_list)),
                )
            )

        # FastAPI/Starlette 解析 multipart 后已知道各文件的实际大小；
        # 在逐个处理前先拒绝总量超限，避免前面的文件已入库后才发现超限。
        file_sizes = [getattr(file, "size", None) for file in file_list]
        if any(size is None for size in file_sizes):
            raise ValueError("无法确认上传文件总大小")
        total_size = sum(size for size in file_sizes if size is not None)
        if total_size > upload_config.max_total_upload_size:
            raise ValueError(
                t(
                    I18nKey.UPLOAD_TOTAL_SIZE_EXCEEDED,
                    max_mb=str(upload_config.max_total_upload_size // MIB),
                )
            )

        # 逐文件独立处理：读取 → 校验 → 写盘 → 入库 → 释放内存
        # 单循环设计：任意时刻内存最多持有 1 个文件，避免批量 OOM
        for file in file_list:
            file_name = Path(file.filename or "unnamed").name
            suffix = Path(file_name).suffix.lower()

            # 类型白名单校验
            if not upload_config.is_type_allowed(suffix):
                failed_files.append(
                    {
                        "filename": file_name,
                        "file_size": 0,
                        "file_sha256": "",
                        "error": t(
                            I18nKey.UPLOAD_TYPE_REJECTED,
                            suffix=suffix or t(I18nKey.UPLOAD_NO_EXTENSION),
                            allowed=", ".join(allowed_exts),
                        ),
                    }
                )
                continue

            # 单文件大小预检：超限时不再读取文件内容。
            max_size = upload_config.get_max_size_for_ext(suffix)
            file_size = file.size
            if file_size > max_size:
                failed_files.append(
                    {
                        "filename": file_name,
                        "file_size": file_size,
                        "file_sha256": "",
                        "error": t(
                            I18nKey.UPLOAD_SIZE_EXCEEDED,
                            max_mb=str(max_size // MIB),
                        ),
                    }
                )
                continue

            chunks: list[bytes] = []
            while True:
                chunk = await file.read(MIB)  # 1 MiB 分块
                if not chunk:
                    break
                chunks.append(chunk)

            content = b"".join(chunks)

            try:
                validate_upload_content(suffix, content)
            except ValueError:
                failed_files.append(
                    {
                        "filename": file_name,
                        "file_size": file_size,
                        "file_sha256": "",
                        "error": t(I18nKey.UPLOAD_CONTENT_INVALID),
                    }
                )
                continue

            logger.info(
                "收到用户上传文件 | user_id=%s | device=%s | filename=%s | size=%s | type=%s",
                user_id if user_id is not None else "anon",
                device_id[:8] if device_id else "-",
                repr(file_name),
                len(content),
                suffix,
            )

            # ── 处理该文件：写盘 → 入库（content 处理后离开作用域释放）──
            file_uid = generate_uuid_hex()
            file_sha256 = sha256_hex(content)
            file_path: Path | None = None
            ingest_started = False

            try:
                file_path = UploadFileStore.build_file_path(
                    file_uid,
                    file_name,
                    suffix,
                )
                await UploadFileStore.store_content(file_path, content, executor)

                # ── 阶段2：逐文件入库向量库（携带 file_uid 写入 chunk metadata）──
                ingest_started = True
                index_result = await rag_app.ingest_files(
                    [str(file_path.resolve())],
                    cancellation_token=cancellation_token,
                    file_uid=file_uid,
                    disk_file_at=now_iso(),
                    file_name=file_name,
                )

                # ── 阶段3：确认入库结果 ──
                indexed_shas = {item["file_sha256"] for item in index_result["indexed"]}
                skipped_shas = {item["file_sha256"] for item in index_result["skipped"]}

                if file_sha256 in indexed_shas:
                    await run_in_pool(
                        get_database_query_pool(),
                        record_upload_metadata,
                        file_uid,
                        file_sha256,
                        str(file_path.resolve()),
                        len(content),
                        user_id,
                        device_id,
                    )
                    success_files.append(
                        {
                            "filename": file_name,
                            "file_uid": file_uid,
                        }
                    )
                elif file_sha256 in skipped_shas:
                    existing_file_path = next(
                        (
                            item.get("existing_file_path")
                            for item in index_result["skipped"]
                            if item["file_sha256"] == file_sha256
                        ),
                        None,
                    )
                    if (
                        existing_file_path
                        and file_path is not None
                        and Path(existing_file_path).is_file()
                    ):
                        UploadFileStore.remove_file(file_path)
                    duplicate_files.append({"filename": file_name})
                    logger.info(
                        "文件上传成功 | filename=%s | sha=%s",
                        file_name,
                        file_sha256[:16],
                    )
                else:
                    raise RuntimeError(t(I18nKey.UPLOAD_VECTOR_DB_ERROR))

            except asyncio.CancelledError:
                _rollback_file(
                    file_path,
                    file_uid,
                    rag_app if ingest_started else None,
                )
                failed_files.append(
                    {"filename": file_name, "error": "上传被客户端取消"}
                )
                raise

            except Exception as e:
                _rollback_file(
                    file_path,
                    file_uid,
                    rag_app if ingest_started else None,
                )
                logger.warning(
                    "文件上传失败已回滚 | filename=%s | sha=%s | error=%s",
                    file_name,
                    file_sha256[:16],
                    e,
                )
                failed_files.append({"filename": file_name, "error": str(e)})

        logger.info(
            "批量上传完成 | 总计=%d | 成功=%d | 失败=%d",
            len(file_list),
            len(success_files),
            len(failed_files),
        )
        return {
            "success_files": success_files,
            "duplicate_files": duplicate_files,
            "failed_files": failed_files,
        }


def _rollback_file(
    file_path: Path | None,
    file_uid: str,
    rag_app: RAGContainer | None,
):
    """回滚单个文件的向量库和磁盘文件。

    顺序：向量库 → 磁盘。向量库失败时中断回滚并保留磁盘文件，
    避免删掉 DB 仍引用的源文件。

    向量库删除使用本次上传唯一的 file_uid。
    """
    # 1. 先删向量库（失败则中断，不继续删磁盘）
    if rag_app:
        try:
            deleted = rag_app.delete_by_uid(file_uid)
            if deleted:
                logger.info("回滚向量库 | uid=%s | deleted=%d", file_uid[:16], deleted)
        except Exception as e:
            logger.error(
                "回滚向量库失败，中断回滚 | uid=%s | error=%s",
                file_uid[:16],
                e,
            )
            return  # 不继续删磁盘/缓存，保留可重试状态

    # 2. 删磁盘文件
    if file_path is not None:
        UploadFileStore.remove_file(file_path)
