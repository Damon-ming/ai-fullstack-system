# app-server/src/com/damon/ming/router/upload/service/upload_file_storage.py
"""上传文件的磁盘存储和可选 SHA-256 路径缓存。"""

import asyncio
import os
from collections import OrderedDict
from pathlib import Path
from typing import ClassVar

from src.com.damon.ming.app.thread_pools import run_in_pool
from src.com.damon.ming.log import pin

logger = pin("upload.file_store")


class UploadFileStorage:
    """管理上传目录、原子写盘和可选的 SHA-256 路径缓存。"""

    upload_dir: ClassVar[Path]
    _sha_cache: ClassVar[OrderedDict[tuple[str, str], Path]] = OrderedDict()
    _sha_cache_max: ClassVar[int]

    @classmethod
    def set_knowledge_dir(cls, knowledge_dir: str) -> None:
        cls.upload_dir = Path(knowledge_dir).resolve()
        cls.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info("上传文件目录已设置 | path=%s", cls.upload_dir)

    @classmethod
    def init_sha_cache(cls, sha_cache_max: int) -> None:
        """初始化空缓存；上传流程暂不读写缓存，后续接入时复用此能力。"""
        if sha_cache_max < 1:
            raise ValueError("sha_cache_max 必须为正整数")
        cls._sha_cache_max = sha_cache_max
        cls._sha_cache.clear()

        tmp_cleaned = 0
        for path in cls.upload_dir.rglob("*.tmp"):
            if path.is_file():
                try:
                    path.unlink(missing_ok=True)
                    tmp_cleaned += 1
                except OSError:
                    logger.exception("启动清理残留临时文件失败 | path=%s", path)
        if tmp_cleaned:
            logger.info("启动清理残留临时文件 | count=%d", tmp_cleaned)

        logger.info("SHA-256 路径缓存已初始化 | max=%d", sha_cache_max)

    @classmethod
    def get_cached_file(cls, file_sha256: str, suffix: str) -> Path | None:
        """获取缓存的磁盘路径；缓存路径失效时自动移除。当前上传流程未调用。"""
        key = (file_sha256, suffix.lower())
        cached_path = cls._sha_cache.get(key)
        if cached_path is None:
            return None
        if not cached_path.is_file():
            cls._sha_cache.pop(key, None)
            return None
        cls._sha_cache.move_to_end(key)
        return cached_path

    @classmethod
    def cache_file(cls, file_sha256: str, suffix: str, file_path: Path) -> None:
        """登记 SHA 到磁盘路径的映射并按上限执行 LRU 淘汰。

        当前上传流程未调用。
        """
        key = (file_sha256, suffix.lower())
        cls._sha_cache[key] = file_path
        cls._sha_cache.move_to_end(key)
        while len(cls._sha_cache) > cls._sha_cache_max:
            cls._sha_cache.popitem(last=False)

    @classmethod
    def build_file_path(cls, file_uid: str, file_name: str, suffix: str) -> Path:
        safe_name = file_name.replace("/", "_").replace("\\", "_").replace("\0", "")
        sub_folder = suffix.lstrip(".") if suffix else "no_ext"
        target_dir = cls.upload_dir / sub_folder
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{file_uid}_{safe_name}"

    @staticmethod
    async def store_content(file_path: Path, content: bytes, executor) -> None:
        write_task = asyncio.create_task(
            run_in_pool(executor, _write_file_sync, file_path, content)
        )
        try:
            await asyncio.shield(write_task)
        except asyncio.CancelledError:
            # 线程池任务无法被 asyncio 取消；等待写盘结束后再让上传层回滚。
            try:
                await write_task
            except Exception:
                logger.exception("取消期间写盘任务失败 | path=%s", file_path)
            raise

    @staticmethod
    def remove_file(file_path: Path) -> bool:
        try:
            file_path.unlink(missing_ok=True)
            for key, cached_path in UploadFileStorage._sha_cache.items():
                if cached_path == file_path:
                    UploadFileStorage._sha_cache.pop(key, None)
            return True
        except OSError:
            logger.warning("回滚删除磁盘文件失败 | path=%s", file_path)
            return False

    @staticmethod
    def move_to_temporary(file_path: Path) -> bool:
        """回滚删除失败时改名，留待下次启动清理。"""
        if not file_path.exists():
            return True
        temporary_path = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            os.replace(file_path, temporary_path)
            for key, cached_path in UploadFileStorage._sha_cache.items():
                if cached_path == file_path:
                    UploadFileStorage._sha_cache.pop(key, None)
            logger.warning(
                "磁盘文件删除失败，已改名为待清理临时文件 | path=%s",
                temporary_path,
            )
            return True
        except OSError:
            logger.exception("回滚文件改名为临时文件失败 | path=%s", file_path)
            return False


def _write_file_sync(path: Path, content: bytes) -> None:
    """先写临时文件，完成后原子改名为正式文件。"""
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
