"""上传文件的磁盘存储与 SHA 缓存。"""

import asyncio
import os
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
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
class _ContentLockEntry:
    lock: asyncio.Lock
    users: int = 0


@dataclass
class StoredUploadFile:
    """一次存储操作的状态，供向量入库失败时回滚。"""

    file_path: Path
    cache_key: tuple[str, str]
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
    _sha_cache: ClassVar[OrderedDict[tuple[str, str], Path]] = OrderedDict()
    _sha_cache_lock: ClassVar[threading.Lock] = threading.Lock()
    _sha_cache_max: ClassVar[int]
    _content_locks: ClassVar[dict[tuple[str, str], _ContentLockEntry]] = {}
    _content_locks_guard: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    @asynccontextmanager
    async def lock_content(cls, file_sha256: str, suffix: str):
        """串行化相同内容、相同格式的完整上传提交流程。"""
        key = (file_sha256, suffix)
        with cls._content_locks_guard:
            entry = cls._content_locks.get(key)
            if entry is None:
                entry = _ContentLockEntry(lock=asyncio.Lock())
                cls._content_locks[key] = entry
            entry.users += 1

        try:
            async with entry.lock:
                yield
        finally:
            with cls._content_locks_guard:
                entry.users -= 1
                if entry.users == 0 and cls._content_locks.get(key) is entry:
                    cls._content_locks.pop(key, None)

    @classmethod
    def set_knowledge_dir(cls, knowledge_dir: str) -> None:
        cls.upload_dir = Path(knowledge_dir).resolve()
        cls.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info("上传文件目录已设置 | path=%s", cls.upload_dir)

    @classmethod
    def init_sha_cache(cls, sha_cache_max: int) -> None:
        cls._sha_cache_max = sha_cache_max
        logger.info("初始化文件 sha256 缓存 | sha_cache_max=%d", sha_cache_max)
        cache: OrderedDict[tuple[str, str], Path] = OrderedDict()
        tmp_cleaned = 0
        for path in cls.upload_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.endswith(".tmp"):
                path.unlink(missing_ok=True)
                tmp_cleaned += 1
                continue
            sha = sha256_file(path)
            cache[(sha, path.suffix.lower())] = path
            if len(cache) > sha_cache_max:
                evicted_key, _ = cache.popitem(last=False)
                logger.debug(
                    "sha_cache 启动扫描 LRU 淘汰 | sha=%s | suffix=%s",
                    evicted_key[0][:16],
                    evicted_key[1],
                )
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
        suffix: str,
        content: bytes,
        executor,
    ) -> StoredUploadFile:
        cache_key = (file_sha256, suffix)
        stored_file = StoredUploadFile(file_path=file_path, cache_key=cache_key)

        with cls._sha_cache_lock:
            cached_path = cls._sha_cache.get(cache_key)

        if cached_path is not None:
            if cached_path.is_file():
                with cls._sha_cache_lock:
                    if cls._sha_cache.get(cache_key) == cached_path:
                        cls._sha_cache.move_to_end(cache_key)
                        stored_file.cache_hit = True
                        stored_file.disk_path = cached_path
                        return stored_file
            with cls._sha_cache_lock:
                if cls._sha_cache.get(cache_key) == cached_path:
                    cls._sha_cache.pop(cache_key, None)

        await run_in_pool(executor, _write_file_sync, file_path, content)
        stored_file.written_to_disk = True

        with cls._sha_cache_lock:
            cached_path = cls._sha_cache.get(cache_key)
            if cached_path is not None and not cached_path.is_file():
                cls._sha_cache.pop(cache_key, None)
                cached_path = None
            if cached_path is not None and cached_path != file_path:
                file_path.unlink(missing_ok=True)
                stored_file.written_to_disk = False
                stored_file.cache_hit = True
                stored_file.disk_path = cached_path
                cls._sha_cache.move_to_end(cache_key)
            else:
                cls._sha_cache[cache_key] = file_path
                cls._sha_cache.move_to_end(cache_key)
                if len(cls._sha_cache) > cls._sha_cache_max:
                    cls._sha_cache.popitem(last=False)
                stored_file.cache_added = True
                stored_file.disk_path = file_path

        return stored_file

    @classmethod
    def rollback_storage(cls, stored_file: StoredUploadFile) -> None:
        if stored_file.written_to_disk:
            try:
                stored_file.file_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("回滚删除磁盘文件失败 | path=%s", stored_file.file_path)

        if stored_file.cache_added:
            with cls._sha_cache_lock:
                if cls._sha_cache.get(stored_file.cache_key) == stored_file.file_path:
                    cls._sha_cache.pop(stored_file.cache_key, None)


def _write_file_sync(path: Path, content: bytes) -> None:
    """原子写入临时文件并重命名到正式路径。"""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp_path.open("wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.rename(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("写入失败后清理临时文件失败 | path=%s", tmp_path)
        raise
