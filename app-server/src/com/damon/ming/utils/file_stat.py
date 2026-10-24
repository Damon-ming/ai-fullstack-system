# app-server/src/com/damon/ming/utils/file_stat.py
"""
文件 stat 工具 —— 跨平台获取文件创建时间。

Linux 没有可靠的 st_birthtime，st_ctime 是元数据修改时间（不可靠）。
知识库文件写入后不再修改，因此 st_mtime 最接近创建时间。
Windows 上优先使用 st_ctime（真正的创建时间）。
"""

import os
from datetime import UTC, datetime


def file_creation_time(path: str | os.PathLike) -> datetime:
    """获取文件创建时间（跨平台兼容）。

    优先级：
      1. st_birthtime（macOS / 部分 BSD）
      2. st_ctime（Windows = 创建时间；Linux = 元数据修改时间）
      3. st_mtime（兜底，Linux 上最接近创建时间）

    Returns:
        UTC datetime。
    """
    stat = os.stat(path)
    # getattr 兜底：Windows 有 st_ctime 但未来会废弃，macOS 有 st_birthtime
    timestamp = getattr(stat, "st_birthtime", getattr(stat, "st_ctime", stat.st_mtime))
    return datetime.fromtimestamp(timestamp, tz=UTC)


def file_size(path: str | os.PathLike) -> int:
    """获取文件 size（bytes）。"""
    return os.stat(path).st_size
