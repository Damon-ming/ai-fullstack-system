# app-server/src/com/damon/ming/utils/time.py
"""
时间工具 —— 业务层获取当前时间的统一入口。

集中管理便于：
  - 测试时 mock 一个函数而非四处 patch datetime.now
  - 未来需要切换时区或时钟策略时只改一处
"""

from datetime import UTC, datetime


def now() -> datetime:
    """获取当前 UTC 时间。"""
    return datetime.now(UTC)


def unix_timestamp() -> int:
    """获取当前 Unix 时间戳（秒）。"""
    return int(datetime.now(UTC).timestamp())
