# app-server/src/com/damon/ming/upload/service/upload_service.py
import asyncio
import hashlib
import threading
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import ClassVar

from fastapi import UploadFile
from src.com.damon.ming.ai.rag_tool import RAGContainer
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.upload.schemas.bean import (
    FileUploadRequest,
)
from src.com.damon.ming.thread import CancellationToken

logger = pin("upload.service")

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "knowledges"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class UploadService:
    """上传服务——逐文件原子提交：每个文件独立走 磁盘+缓存+向量库 三步，
    三步全部成功才算成功；任一步失败则回滚该文件的磁盘和缓存，通知客户端重试。
    """

    _sha_cache: ClassVar[OrderedDict[str, Path]] = OrderedDict()
    _sha_cache_lock: ClassVar[threading.Lock] = threading.Lock()
    _sha_cache_max: ClassVar[int] = 0  # 由 init_sha_cache() 从配置注入

    @classmethod
    def init_sha_cache(cls, sha_cache_max: int = 10000):
        """服务启动时，一次性扫描知识库构建sha缓存，在main.py lifespan调用。

        Args:
            sha_cache_max: sha_cache LRU 上限，由上传配置注入。
        """
        cls._sha_cache_max = sha_cache_max
        logger.info("初始化文件sha256缓存 | sha_cache_max=%d", sha_cache_max)
        cache: OrderedDict[str, Path] = OrderedDict()
        for p in UPLOAD_DIR.rglob("*"):
            if p.is_file():
                sha = _file_sha256(p)
                cache[sha] = p
                # 启动扫描也受 LRU 上限约束，避免超大知识库启动时内存爆炸
                if len(cache) > sha_cache_max:
                    evicted_sha, _ = cache.popitem(last=False)
                    logger.debug("sha_cache 启动扫描LRU淘汰 | sha=%s", evicted_sha[:16])
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
        prepared_files: list[tuple[str, bytes]] = []
        allowed_exts = sorted(upload_config.allowed_types.keys())

        # 阶段0：完整读取并准备所有文件；任一文件读取失败仅跳过该文件，
        # 不会写入磁盘，避免产生半上传结果。
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
                        "error": f"不支持的文件类型: {suffix or '无扩展名'}，仅允许: {', '.join(allowed_exts)}",
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
                            f"文件过大（上限 {max_size // (1024 * 1024)}MB）"
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
            logger.info(
                "收到用户上传文件 | original_filename=%s | size=%s | type=%s",
                origin_name,
                len(content),
                suffix,
            )
            prepared_files.append((origin_name, content))

        # 阶段1+2+3：逐文件独立处理（写盘 + 缓存 + 入库）
        loop = asyncio.get_running_loop()

        for origin_name, content in prepared_files:
            suffix = Path(origin_name).suffix.lower()
            file_uid = uuid.uuid4().hex
            file_sha256 = hashlib.sha256(content).hexdigest()

            # 构建存储路径
            sub_folder_name = suffix.lstrip(".") if suffix else "no_ext"
            target_base_dir = UPLOAD_DIR / sub_folder_name
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

                # ── 阶段2：逐文件入库向量库 ──
                index_result = rag_app.ingest_files(
                    [str(disk_path.resolve())],
                    cancellation_token=cancellation_token,
                )

                # ── 阶段3：确认入库结果 ──
                indexed_shas = {item["file_sha256"] for item in index_result["indexed"]}
                skipped_shas = {item["file_sha256"] for item in index_result["skipped"]}

                if file_sha256 in indexed_shas or file_sha256 in skipped_shas:
                    # 三库一致：成功
                    success_files.append({"filename": origin_name})
                    logger.info(
                        "文件上传成功 | filename=%s | sha=%s",
                        origin_name,
                        file_sha256[:16],
                    )
                else:
                    # 入库结果中没有这个文件 → 视为失败
                    raise RuntimeError("向量库入库结果异常，未找到该文件")

            except asyncio.CancelledError:
                # 客户端取消：回滚并继续
                _rollback_file(file_path, file_sha256, written_to_disk, cache_added)
                failed_files.append(
                    {"filename": origin_name, "error": "上传被客户端取消"}
                )
                raise

            except Exception as e:
                # 任一步失败：回滚该文件的磁盘 + 缓存
                _rollback_file(file_path, file_sha256, written_to_disk, cache_added)
                logger.warning(
                    "文件上传失败已回滚 | filename=%s | sha=%s | error=%s",
                    origin_name,
                    file_sha256[:16],
                    e,
                )
                failed_files.append({"filename": origin_name, "error": str(e)})

        logger.info(
            "批量上传完成 | 总计=%d | 成功=%d | 失败=%d",
            len(prepared_files),
            len(success_files),
            len(failed_files),
        )
        return {"files": success_files, "failed_files": failed_files}


def _rollback_file(
    file_path: Path, file_sha256: str, written_to_disk: bool, cache_added: bool
):
    """回滚单个文件的磁盘和缓存，保持三库一致。"""
    if written_to_disk:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("回滚删除磁盘文件失败 | path=%s", file_path)

    if cache_added:
        with UploadService._sha_cache_lock:
            # 只有缓存值仍指向我们的路径才删除（防止被并发覆盖）
            if UploadService._sha_cache.get(file_sha256) == file_path:
                UploadService._sha_cache.pop(file_sha256, None)


def _write_file_sync(path: Path, content: bytes) -> None:
    """同步写盘（在 run_in_executor 中调用，不阻塞事件循环）"""
    with path.open("wb") as f:
        f.write(content)


def _file_sha256(path: Path) -> str:
    """读取磁盘文件，分块计算sha256哈希"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
