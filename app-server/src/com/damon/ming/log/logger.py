"""统一日志模块 —— 业务层只需调用 pin(name) 获取 logger。

初始化：
  服务端启动时由 main.py 调用 init_logging(is_debug)，注入环境标志。
  - debug：完整输出到 stdout，含堆栈
  - release：输出到 logs/app.log 文件，不泄漏到容器日志采集

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
    """初始化日志系统，由服务端启动时调用一次。

    参数：
      is_debug: 来自 src.com.damon.ming.debug.is_debug()，
               构建时/启动时冻结，运行时不可变。
    """
    global _root_configured
    root_logger = logging.getLogger()

    if root_logger.handlers:
        _root_configured = True
        return

    level = _LOG_LEVELS.get(os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    if is_debug:
        logging.basicConfig(
            level=level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
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
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        root_logger.addHandler(file_handler)

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


def security_warn(message: str) -> None:
    """发出安全配置警告（弱密钥、不安全配置等）。

    统一通过日志模块输出，WARNING 级别，命名空间为 security。
    替代直接使用标准库 warnings.warn，便于统一管理和过滤。
    """
    get_logger("security").warning(message)
