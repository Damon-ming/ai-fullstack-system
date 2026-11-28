# app-server/src/com/damon/ming/router/upload/service/upload_file_storage.py
"""上传文件的磁盘存储和临时文件清理。"""

import asyncio
import os
import re
from pathlib import Path

from src.com.damon.ming.app.thread_pools import get_io_pool, run_in_pool
from src.com.damon.ming.log import pin

logger = pin("upload.file_store")


class UploadFileStorage:
    """管理上传目录、原子写盘和磁盘文件清理。"""

    upload_dir: Path

    @classmethod
    def set_corpus_dir(cls, corpus_dir: str) -> None:
        cls.upload_dir = Path(corpus_dir).resolve()
        cls.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info("上传文件目录已设置 | path=%s", cls.upload_dir)

    @classmethod
    def clean_temporary_files(cls) -> None:
        """启动时清理上次运行遗留的临时文件。"""
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

    @classmethod
    def build_file_path(
        cls, user_id: int, user_name: str, file_id: str, file_name: str, suffix: str
    ) -> Path:
        """构造 corpus/{user_id}-{name}/{扩展名}/{file_id}_{文件名}。"""
        safe_user_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", user_name).strip(" .")
        safe_name = file_name.replace("/", "_").replace("\\", "_").replace("\0", "")
        sub_folder = suffix.lstrip(".") if suffix else "no_ext"
        target_dir = (
            cls.upload_dir / f"{user_id}-{safe_user_name or '用户'}" / sub_folder
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{file_id}_{safe_name}"

    @staticmethod
    async def store_content(file_path: Path, content: bytes) -> None:
        write_task = asyncio.create_task(
            run_in_pool(get_io_pool(), _write_file_sync, file_path, content)
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
