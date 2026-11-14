# app-server/src/com/damon/ming/log/logger.py
"""统一日志模块 —— 业务层只需调用 pin(name) 获取 logger。

初始化：
  服务端启动时由 main.py 调用 init_logging(is_debug)，通过参数注入环境标志。
  - debug：完整输出到 stdout，含堆栈
  - release：输出到 logs/app.log 文件，不泄漏到容器日志采集
  - 日志级别由 LOG_LEVEL 环境变量决定（默认 INFO），读取入口在 app/config/env.py

TODO: release 环境日志加密上传云端
  - 本地日志文件按日滚动，达到阈值后加密打包
  - 上传至云端日志服务（如 AWS CloudWatch / 阿里云 SLS）
  - 加密密钥由 KMS 管理，不落盘
  - 优先级：P1，当前 release 日志写本地文件，后续迭代接入云端
"""

import logging
import os
import sys

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_root_configured = False


def init_logging(is_debug: bool) -> None:
    """初始化日志系统，由调用方传入环境标志，不依赖 debug 包。"""
    global _root_configured
    root_logger = logging.getLogger()

    if root_logger.handlers:
        _root_configured = True
        return

    # 延迟导入：log 是基础模块，而 app.config.env 会触发 app 包初始化，
    # app_initializer 又依赖 log —— 模块级导入会形成循环依赖
    from src.com.damon.ming.app.config.env import get_log_level

    level_name = get_log_level()
    level = _LOG_LEVELS.get(level_name, logging.INFO)

    log_fmt = (
        "%(asctime)s | %(levelname)-8s | %(process)d | %(threadName)-15s "
        "| %(name)s | %(filename)s:%(lineno)d | %(message)s"
    )

    formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S.%f")

    if is_debug:
        logging.basicConfig(
            level=level,
            format=log_fmt,
            datefmt="%Y-%m-%d %H:%M:%S.%f",
            stream=sys.stdout,
        )
    else:
        # release：输出到文件，不打印到 stdout（防止敏感信息泄漏到容器日志采集系统）
        _log_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "logs"
        )
        os.makedirs(_log_dir, exist_ok=True)
        _log_file = os.path.join(_log_dir, "app.log")
        file_handler = logging.FileHandler(_log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        # root 默认级别是 WARNING，不显式降级会让 INFO 根本写不进文件
        root_logger.setLevel(level)

    if level_name not in _LOG_LEVELS:
        root_logger.warning(
            "LOG_LEVEL=%r 无效，已回退为 INFO（可选：%s）",
            level_name,
            ", ".join(_LOG_LEVELS),
        )

    _root_configured = True


def get_logger(name: str) -> logging.Logger:
    """按模块名获取日志对象。"""
    return logging.getLogger(name)


def pin(tag: str) -> logging.Logger:
    """兼容旧代码的日志入口，保留 pin(name) 调用方式。

    注意：init_logging() 之前 pin() 返回的是未配置的 root logger，
    建议在服务端启动时尽早调用 init_logging()。
    """
    return get_logger(tag)
