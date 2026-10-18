# app-server/src/com/damon/ming/upload/service/upload_service.py
import asyncio
import hashlib
import threading
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import ClassVar

from fastapi import UploadFile
from src.com.damon.ming.ai.rag_tool import get_rag_container
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.upload.schemas.bean import (
    FileUploadRequest,
)
from src.com.damon.ming.thread import CancellationToken

logger = pin("upload.service")

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "knowledges"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class UploadService:
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
        cancellation_token: CancellationToken | None = None,
    ) -> list[dict]:
        # 移除全局 _processing_lock：各层已有细粒度锁保护
        #   - sha_cache 读写 → _sha_cache_lock
        #   - 向量库去重 + 入库 → RAGContainer._knowledge_lock
        #   - BM25 索引重建 → BM25Index._rw_lock (RLock)
        # 并发上传同一文件的边界：各自写 UUID 副本 → ingest_files 向量库去重只索引一份
        return await UploadService._batch_save_files_locked(
            file_list, upload_config, cancellation_token
        )

    @staticmethod
    async def _batch_save_files_locked(
        file_list: list[UploadFile],
        upload_config,
        cancellation_token: CancellationToken | None = None,
    ) -> list[dict]:
        """
        批量保存文件
        :param file_list: 上传文件数组
        :param upload_config: UploadConfig 实例（文件类型白名单 + 大小上限）
        :param cancellation_token: 请求级取消令牌
        :return: 文件信息列表
        """
        saved_files = []
        files_to_index = []
        prepared_files = []
        allowed_exts = sorted(upload_config.allowed_types.keys())
        # 先完整读取并准备本次请求的所有文件；任一文件读取失败时，此阶段不会写入磁盘，避免多文件请求产生半上传结果。
        for file in file_list:
            origin_name = Path(file.filename or "unnamed").name
            suffix = Path(origin_name).suffix.lower()

            # 类型白名单校验：不在配置中的扩展名直接拒绝
            if not upload_config.is_type_allowed(suffix):
                raise ValueError(
                    f"不支持的文件类型: {suffix or '无扩展名'}（{origin_name}），"
                    f"仅允许: {', '.join(allowed_exts)}"
                )

            # 大小校验：按类型匹配上限（边读边校验，超限立即中断，
            # 避免恶意大文件一次性读入内存导致 OOM）
            max_size = upload_config.get_max_size_for_ext(suffix)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB 分块
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    raise ValueError(
                        f"文件过大: {origin_name}（>"
                        f"{max_size // (1024 * 1024)}MB），"
                        f"该类型上限 {max_size // (1024 * 1024)}MB"
                    )
                chunks.append(chunk)
            content = b"".join(chunks)

            logger.info(
                "收到用户上传文件 | original_filename=%s | size=%s | type=%s",
                origin_name,
                len(content),
                suffix,
            )
            prepared_files.append((file, origin_name, content))

        loop = asyncio.get_running_loop()

        for file, origin_name, content in prepared_files:
            file_uid = uuid.uuid4().hex
            # 磁盘文件名完全不使用用户文件名，只保留随机标识和安全扩展名。
            suffix = Path(origin_name).suffix.lower()

            if suffix:
                sub_folder_name = suffix.lstrip(".")
            else:
                sub_folder_name = "no_ext"

            target_base_dir = UPLOAD_DIR / sub_folder_name
            target_base_dir.mkdir(parents=True, exist_ok=True)

            store_name = f"{file_uid}{suffix}"
            file_path = target_base_dir / store_name

            logger.debug(
                "开始保存文件 | filename=%s | size=%s", origin_name, len(content)
            )

            digest = hashlib.sha256(content)
            file_sha256 = digest.hexdigest()

            # M5: 锁仅覆盖 sha_cache 读写，写盘移到锁外 + executor
            # 先检查缓存，命中则跳过写盘
            cache_hit = False
            with UploadService._sha_cache_lock:
                existing = UploadService._sha_cache.get(file_sha256)
                if existing:
                    cache_hit = True
                    # M3: 更新 LRU 顺序（命中 → 移到末尾）
                    UploadService._sha_cache.move_to_end(file_sha256)

            if cache_hit:
                saved_files.append(
                    {
                        "filename": origin_name,
                        "save_path": str(existing),
                        "file_size": existing.stat().st_size,
                        "file_sha256": file_sha256,
                        "duplicate": True,
                    }
                )
                # 即使本地文件已存在，也交给幂等入库流程检查一次，修复 "文件已保存但服务重启前入库失败"的半成品状态。
                files_to_index.append(str(existing.resolve()))
                continue

            # M2: 同步写盘提交到线程池，不阻塞事件循环
            await loop.run_in_executor(None, _write_file_sync, file_path, content)

            # M3 + M5: 锁仅覆盖 cache 更新，含 LRU 淘汰
            with UploadService._sha_cache_lock:
                UploadService._sha_cache[file_sha256] = file_path
                UploadService._sha_cache.move_to_end(file_sha256)
                if len(UploadService._sha_cache) > UploadService._sha_cache_max:
                    evicted_sha, _ = UploadService._sha_cache.popitem(last=False)
                    logger.debug("sha_cache LRU 淘汰 | sha=%s", evicted_sha[:16])

            saved_files.append(
                {
                    "filename": origin_name,
                    "save_path": str(file_path),
                    "file_size": len(content),
                    "file_sha256": file_sha256,
                    "duplicate": False,
                }
            )

            files_to_index.append(str(file_path.resolve()))

        if files_to_index:
            # 这里不回滚磁盘文件：如果后续索引失败，保留文件并打印日志，
            # 下次服务启动时由启动同步逻辑补齐向量库和 BM25。
            try:
                index_result = get_rag_container().ingest_files(
                    files_to_index, cancellation_token=cancellation_token
                )
                indexed_by_md5 = {
                    item["file_sha256"] for item in index_result["indexed"]
                }
                skipped_by_md5 = {
                    item["file_sha256"] for item in index_result["skipped"]
                }
                for item in saved_files:
                    item["duplicate"] = item.get("file_sha256") in skipped_by_md5
                    item["indexed"] = (
                        item.get("file_sha256") in indexed_by_md5 or item["duplicate"]
                    )
            except Exception:
                logger.exception(
                    "文件已保存，但知识库增量同步失败；服务重启后将自动补偿 | paths=%s",
                    files_to_index,
                )
                raise
        logger.info("文件保存完成 | count=%s", len(saved_files))
        return saved_files


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
