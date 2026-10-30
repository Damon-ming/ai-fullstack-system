# app-server/src/com/damon/ming/upload/service/upload_service.py
import asyncio
import hashlib
import os
import threading
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import ClassVar

from fastapi import UploadFile
from sqlalchemy import text
from src.com.damon.ming.ai.rag_tool import RAGContainer
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.upload.schemas.bean import (
    FileUploadRequest,
)
from src.com.damon.ming.thread import CancellationToken
from src.com.damon.ming.utils.file_stat import file_creation_time
from src.com.damon.ming.utils.time import now_iso

logger = pin("upload.service")


class UploadService:
    """上传服务——逐文件原子提交，多用户并发安全。

    数据一致性保证（已验证）：
      1. 文件原子性：每个文件的 磁盘 + sha缓存 + 向量库 三步持久化，
         要么全部成功，要么全部失败回滚，不存在部分写入。
      2. 批量隔离：逐个文件独立处理，单个文件失败回滚不影响其他文件。
      3. Chat / Upload 隔离：上传走 document_pool 线程池，聊天走 retrieval_pool /
         rerank_pool 线程池，互不阻塞；修复后上传不再卡事件循环。
      4. 上传后立即可读：文件入库 pgvector 后，其他用户的 chat 检索能立即
         查到新文件（稠密检索不受影响；BM25 后台重建期间稀疏检索用旧索引，
         属优雅降级，不丢数据）。
      5. 并发同文件去重：两个用户同时上传内容完全相同的文件（sha256 一致）
         → sha_cache_lock 保证磁盘只存一份 + recheck 机制删除重复磁盘文件
         → knowledge_lock 保证向量库只入库一次（get_by_metadata 去重）
         → 最终：磁盘一份、sha缓存一条、向量库一条，三库一致无冗余。
      6. 审计表无冗余：audit 写入仅在 indexed 时触发（skipped 不写），
         并发同文件只有一个请求进入 indexed 分支，审计表不会出现重复记录。
    """

    upload_dir: ClassVar[Path] = Path(".")  # 由 set_knowledge_dir() 从配置注入
    _sha_cache: ClassVar[OrderedDict[str, Path]] = OrderedDict()
    _sha_cache_lock: ClassVar[threading.Lock] = threading.Lock()
    _sha_cache_max: ClassVar[int] = 0  # 由 init_sha_cache() 从配置注入

    @classmethod
    def set_knowledge_dir(cls, knowledge_dir: str) -> None:
        """设置知识库目录（由 app_initializer 调用，必须在 init_sha_cache 之前）。"""
        cls.upload_dir = Path(knowledge_dir).resolve()
        cls.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info("上传服务知识库目录已设置 | path=%s", cls.upload_dir)

    @classmethod
    def init_sha_cache(cls, sha_cache_max: int = 10000):
        """服务启动时，一次性扫描知识库构建sha缓存，在main.py lifespan调用。

        Args:
            sha_cache_max: sha_cache LRU 上限，由上传配置注入。
        """
        cls._sha_cache_max = sha_cache_max
        logger.info("初始化文件sha256缓存 | sha_cache_max=%d", sha_cache_max)
        cache: OrderedDict[str, Path] = OrderedDict()
        tmp_cleaned = 0
        for p in cls.upload_dir.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.endswith(".tmp"):
                # 崩溃残留的临时文件：写盘未完成，安全删除
                p.unlink(missing_ok=True)
                tmp_cleaned += 1
                continue
            sha = _file_sha256(p)
            cache[sha] = p
            # 启动扫描也受 LRU 上限约束，避免超大知识库启动时内存爆炸
            if len(cache) > sha_cache_max:
                evicted_sha, _ = cache.popitem(last=False)
                logger.debug("sha_cache 启动扫描LRU淘汰 | sha=%s", evicted_sha[:16])
        if tmp_cleaned:
            logger.info("启动清理残留 .tmp 文件 | count=%d", tmp_cleaned)
        with cls._sha_cache_lock:
            cls._sha_cache = cache
        logger.info(f"sha缓存初始化完成，共{len(cache)}个文件")

    @staticmethod
    async def batch_save_files(
        file_list: list[UploadFile],
        req: FileUploadRequest,
        upload_config,
        rag_app: RAGContainer,
        cancellation_token: CancellationToken | None = None,
        executor=None,
        token: str | None = None,
        device_id: str = "",
        db_conn=None,
    ) -> dict:
        """批量保存文件——每个文件独立原子提交。

        逐文件处理，每个文件走完整生命周期：
          1. 校验类型/大小
          2. 写磁盘 + 更新 sha_cache（锁内 check + 锁外写盘 + 锁内 recheck）
          3. 逐文件入库向量库
          4. 任一步失败 → 回滚该文件的磁盘和缓存，标记失败，继续处理下一个

        每个文件互不影响，一个失败不会中断其他文件。

        Returns:
            {"files": [成功文件meta...], "failed_files": [失败文件信息...]}
        """
        success_files: list[dict] = []
        failed_files: list[dict] = []
        allowed_exts = sorted(upload_config.allowed_types.keys())
        total_uploaded = 0  # 累计已读字节数（总量上限防护）
        loop = asyncio.get_running_loop()

        # 文件数量校验
        if len(file_list) > upload_config.max_files_per_request:
            raise ValueError(
                t(
                    I18nKey.UPLOAD_TOO_MANY_FILES,
                    max_files=str(upload_config.max_files_per_request),
                    actual=str(len(file_list)),
                )
            )

        # 逐文件独立处理：读取 → 校验 → 写盘 → 入库 → 释放内存
        # 单循环设计：任意时刻内存最多持有 1 个文件，避免批量 OOM
        for file in file_list:
            origin_name = Path(file.filename or "unnamed").name
            suffix = Path(origin_name).suffix.lower()

            # 类型白名单校验
            if not upload_config.is_type_allowed(suffix):
                failed_files.append(
                    {
                        "filename": origin_name,
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

            # 大小校验（边读边校验，超限立即中断）
            max_size = upload_config.get_max_size_for_ext(suffix)
            chunks: list[bytes] = []
            total = 0
            try:
                while True:
                    chunk = await file.read(1024 * 1024)  # 1MB 分块
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_size:
                        raise ValueError(
                            t(
                                I18nKey.UPLOAD_SIZE_EXCEEDED,
                                max_mb=str(max_size // (1024 * 1024)),
                            )
                        )
                    chunks.append(chunk)
            except ValueError as e:
                failed_files.append(
                    {
                        "filename": origin_name,
                        "file_size": 0,
                        "file_sha256": "",
                        "error": str(e),
                    }
                )
                continue

            content = b"".join(chunks)

            # 总量上限校验（所有文件合计）
            total_uploaded += len(content)
            if total_uploaded > upload_config.max_total_upload_size:
                raise ValueError(
                    t(
                        I18nKey.UPLOAD_TOTAL_SIZE_EXCEEDED,
                        max_mb=str(
                            upload_config.max_total_upload_size // (1024 * 1024)
                        ),
                    )
                )

            logger.info(
                "收到用户上传文件 | token=%s | device=%s | filename=%s | size=%s | type=%s",
                token[:8] if token else "anon",
                device_id[:8] if device_id else "-",
                repr(origin_name),
                len(content),
                suffix,
            )

            # ── 直接处理该文件：写盘 → 缓存 → 入库（content 处理后离开作用域释放）──
            file_uid = uuid.uuid4().hex
            file_sha256 = hashlib.sha256(content).hexdigest()

            # 构建存储路径
            sub_folder_name = suffix.lstrip(".") if suffix else "no_ext"
            target_base_dir = UploadService.upload_dir / sub_folder_name
            target_base_dir.mkdir(parents=True, exist_ok=True)
            store_name = f"{file_uid}{suffix}"
            file_path = target_base_dir / store_name

            written_to_disk = False
            cache_added = False

            try:
                # ── 阶段1：检查缓存（锁内，极小临界区）──
                cache_hit = False
                with UploadService._sha_cache_lock:
                    existing = UploadService._sha_cache.get(file_sha256)
                    if existing:
                        cache_hit = True
                        disk_path = existing

                if not cache_hit:
                    # ── 写盘（锁外，线程池，不阻塞事件循环）──
                    await loop.run_in_executor(
                        executor, _write_file_sync, file_path, content
                    )
                    written_to_disk = True

                    # ── 更新缓存 + 二次检查（锁内，极小临界区）──
                    # 处理并发同文件上传：两个请求同时缓存miss，先写盘者入库，
                    # 后写盘者发现缓存已被更新，删除自己多余的磁盘文件。
                    with UploadService._sha_cache_lock:
                        recheck = UploadService._sha_cache.get(file_sha256)
                        if recheck and recheck != file_path:
                            file_path.unlink(missing_ok=True)
                            written_to_disk = False
                            cache_hit = True
                            disk_path = recheck
                        else:
                            UploadService._sha_cache[file_sha256] = file_path
                            UploadService._sha_cache.move_to_end(file_sha256)
                            if (
                                len(UploadService._sha_cache)
                                > UploadService._sha_cache_max
                            ):
                                UploadService._sha_cache.popitem(last=False)
                            cache_added = True
                            disk_path = file_path

                # ── 记录 disk_file_at：写盘时取当前时间，缓存命中时取磁盘 stat ──
                if not cache_hit:
                    disk_file_at = now_iso()
                else:
                    try:
                        disk_file_at = file_creation_time(str(disk_path)).isoformat()
                    except OSError:
                        disk_file_at = now_iso()

                # ── 阶段2：逐文件入库向量库（携带 file_uid 写入 chunk metadata）──
                index_result = rag_app.ingest_files(
                    [str(disk_path.resolve())],
                    cancellation_token=cancellation_token,
                    file_uid=file_uid,
                    disk_file_at=disk_file_at,
                )

                # ── 阶段3：确认入库结果 ──
                indexed_shas = {item["file_sha256"] for item in index_result["indexed"]}
                skipped_shas = {item["file_sha256"] for item in index_result["skipped"]}

                if file_sha256 in indexed_shas or file_sha256 in skipped_shas:
                    # 三库一致：成功
                    success_files.append(
                        {
                            "filename": origin_name,
                            "file_uid": file_uid,
                        }
                    )

                    # ── 写入审计表（fire-and-forget，不阻塞上传响应）──
                    if db_conn is not None and file_sha256 in indexed_shas:
                        loop.run_in_executor(
                            executor,
                            _record_upload_metadata,
                            db_conn,
                            file_uid,
                            file_sha256,
                            str(disk_path.resolve()),
                            len(content),
                            token,
                            device_id,
                        )

                    logger.info(
                        "文件上传成功 | filename=%s | sha=%s",
                        origin_name,
                        file_sha256[:16],
                    )
                else:
                    # 入库结果中没有这个文件 → 视为失败
                    raise RuntimeError(t(I18nKey.UPLOAD_VECTOR_DB_ERROR))

            except asyncio.CancelledError:
                # 客户端取消：回滚并继续
                _rollback_file(
                    file_path,
                    file_sha256,
                    written_to_disk,
                    cache_added,
                    file_uid=file_uid,
                    rag_app=rag_app,
                )
                failed_files.append(
                    {"filename": origin_name, "error": "上传被客户端取消"}
                )
                raise

            except Exception as e:
                # 任一步失败：回滚该文件的磁盘 + 缓存 + 向量库
                _rollback_file(
                    file_path,
                    file_sha256,
                    written_to_disk,
                    cache_added,
                    file_uid=file_uid,
                    rag_app=rag_app,
                )
                logger.warning(
                    "文件上传失败已回滚 | filename=%s | sha=%s | error=%s",
                    origin_name,
                    file_sha256[:16],
                    e,
                )
                failed_files.append({"filename": origin_name, "error": str(e)})

        logger.info(
            "批量上传完成 | 总计=%d | 成功=%d | 失败=%d",
            len(file_list),
            len(success_files),
            len(failed_files),
        )
        return {"files": success_files, "failed_files": failed_files}


def _rollback_file(
    file_path: Path,
    file_sha256: str,
    written_to_disk: bool,
    cache_added: bool,
    file_uid: str = "",
    rag_app=None,
):
    """回滚单个文件的向量库 / 磁盘 / 缓存，保持三库一致。

    顺序：向量库 → 磁盘 → 缓存。向量库失败时中断回滚并记录，
    避免磁盘已删但向量库仍残留 chunk 的不一致。

    注意：向量库删除使用 file_uid 而非 file_sha256。file_uid 在本次上传中唯一，
    不会跨用户误删（多用户上传相同文件 sha256 一致时，file_uid 各不相同）。
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

    # 2. 删磁盘
    if written_to_disk:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("回滚删除磁盘文件失败 | path=%s", file_path)

    # 3. 删缓存
    if cache_added:
        with UploadService._sha_cache_lock:
            # 只有缓存值仍指向我们的路径才删除（防止被并发覆盖）
            if UploadService._sha_cache.get(file_sha256) == file_path:
                UploadService._sha_cache.pop(file_sha256, None)


def _write_file_sync(path: Path, content: bytes) -> None:
    """同步写盘（在 run_in_executor 中调用，不阻塞事件循环）。

    原子写入：先写 .tmp → fsync → rename。崩溃时残留 .tmp 不影响正式文件，
    启动扫描会自动跳过。
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp_path, path)


def _file_sha256(path: Path) -> str:
    """读取磁盘文件，分块计算sha256哈希"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_upload_metadata(
    db_conn,
    file_uid: str,
    file_sha256: str,
    file_path: str,
    file_size: int,
    token: str | None,
    device_id: str,
) -> None:
    """同步写入 upload_records 审计表（在 run_in_executor 中调用）。

    写入失败记录 error 日志，不影响上传主流程。
    fire-and-forget 场景下任务可能在服务重启时被取消，审计记录可能丢失，
    upload_records 与实际入库文件可能不一致时需排查此日志。
    """
    from datetime import UTC, datetime

    try:
        db_conn.execute(
            text(
                "INSERT INTO upload_records "
                "(file_uid, file_sha256, file_path, file_size, token, device_id, created_at) "
                "VALUES (:uid, :sha, :path, :size, :token, :device, :cat) "
                "ON CONFLICT (file_uid) DO NOTHING"
            ),
            {
                "uid": file_uid,
                "sha": file_sha256,
                "path": file_path,
                "size": str(file_size),
                "token": token[:64] if token else None,
                "device": device_id[:64] if device_id else "",
                "cat": datetime.now(tz=UTC),
            },
            commit=True,
        )
    except Exception as e:
        logger.error(
            "写入审计表失败 | file_uid=%s sha=%s error=%s",
            file_uid[:16],
            file_sha256[:16],
            e,
        )
