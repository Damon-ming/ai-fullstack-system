"""上传文件的磁盘存储与 SHA 缓存。"""

import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from src.com.damon.ming.app.thread_pools import run_in_pool
from src.com.damon.ming.log import pin
from src.com.damon.ming.security.digest import sha256_file
from src.com.damon.ming.utils.file_stat import file_creation_time
from src.com.damon.ming.utils.time import now_iso

logger = pin("upload.file_store")


@dataclass
class StoredUploadFile:
    """一次存储操作的状态，供向量入库失败时回滚。"""

    file_path: Path
    disk_path: Path | None = None
    cache_hit: bool = False
    written_to_disk: bool = False
    cache_added: bool = False

    def get_disk_path(self) -> Path:
        if self.disk_path is None:
            raise RuntimeError("上传文件尚未完成磁盘存储")
        return self.disk_path

    def get_disk_file_at(self) -> str:
        if not self.cache_hit and self.disk_path is not None:
            return now_iso()
        if self.disk_path is not None:
            try:
                return file_creation_time(str(self.disk_path)).isoformat()
            except OSError:
                pass
        return now_iso()


class UploadFileStore:
    """管理上传目录、原子写盘和进程内 SHA-256 LRU 缓存。"""

    upload_dir: ClassVar[Path]
    _sha_cache: ClassVar[OrderedDict[str, Path]] = OrderedDict()
    _sha_cache_lock: ClassVar[threading.Lock] = threading.Lock()
    _sha_cache_max: ClassVar[int]

    @classmethod
    def set_knowledge_dir(cls, knowledge_dir: str) -> None:
        cls.upload_dir = Path(knowledge_dir).resolve()
        cls.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info("上传文件目录已设置 | path=%s", cls.upload_dir)

    @classmethod
    def init_sha_cache(cls, sha_cache_max: int) -> None:
        cls._sha_cache_max = sha_cache_max
        logger.info("初始化文件 sha256 缓存 | sha_cache_max=%d", sha_cache_max)
        cache: OrderedDict[str, Path] = OrderedDict()
        tmp_cleaned = 0
        for path in cls.upload_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.endswith(".tmp"):
                path.unlink(missing_ok=True)
                tmp_cleaned += 1
                continue
            sha = sha256_file(path)
            cache[sha] = path
            if len(cache) > sha_cache_max:
                evicted_sha, _ = cache.popitem(last=False)
                logger.debug("sha_cache 启动扫描 LRU 淘汰 | sha=%s", evicted_sha[:16])
        if tmp_cleaned:
            logger.info("启动清理残留 .tmp 文件 | count=%d", tmp_cleaned)
        with cls._sha_cache_lock:
            cls._sha_cache = cache
        logger.info("sha 缓存初始化完成，共 %d 个文件", len(cache))

    @classmethod
    def build_file_path(cls, file_uid: str, file_name: str, suffix: str) -> Path:
        safe_name = file_name.replace("/", "_").replace("\\", "_").replace("\0", "")
        sub_folder = suffix.lstrip(".") if suffix else "no_ext"
        target_dir = cls.upload_dir / sub_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{file_uid}_{safe_name}"

    @classmethod
    async def store_content(
        cls,
        file_path: Path,
        file_sha256: str,
        content: bytes,
        executor,
    ) -> StoredUploadFile:
        stored_file = StoredUploadFile(file_path=file_path)

        with cls._sha_cache_lock:
            cached_path = cls._sha_cache.get(file_sha256)

        if cached_path is not None:
            return StoredUploadFile(
                file_path=file_path,
                disk_path=cached_path,
                cache_hit=True,
            )

        await run_in_pool(executor, _write_file_sync, file_path, content)
        stored_file.written_to_disk = True

        with cls._sha_cache_lock:
            cached_path = cls._sha_cache.get(file_sha256)
            if cached_path is not None and cached_path != file_path:
                file_path.unlink(missing_ok=True)
                stored_file.written_to_disk = False
                stored_file.cache_hit = True
                stored_file.disk_path = cached_path
            else:
                cls._sha_cache[file_sha256] = file_path
                cls._sha_cache.move_to_end(file_sha256)
                if len(cls._sha_cache) > cls._sha_cache_max:
                    cls._sha_cache.popitem(last=False)
                stored_file.cache_added = True
                stored_file.disk_path = file_path

        return stored_file

    @classmethod
    def rollback_storage(cls, stored_file: StoredUploadFile, file_sha256: str) -> None:
        if stored_file.written_to_disk:
            try:
                stored_file.file_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("回滚删除磁盘文件失败 | path=%s", stored_file.file_path)

        if stored_file.cache_added:
            with cls._sha_cache_lock:
                if cls._sha_cache.get(file_sha256) == stored_file.file_path:
                    cls._sha_cache.pop(file_sha256, None)


def _write_file_sync(path: Path, content: bytes) -> None:
    """原子写入临时文件并重命名到正式路径。"""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.rename(tmp_path, path)
