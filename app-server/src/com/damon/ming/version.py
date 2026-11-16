# app-server/src/com/damon/ming/version.py
"""
版本信息 —— 单一版本源 + CI 构建元信息。

产品版本真值唯一来源：当前工作目录下唯一的 TOML 文件
构建信息由 CI 打包时写入 _build_info.py，本地开发环境自动兜底。

使用方式：
    from src.com.damon.ming.version import VERSION, __version__

VERSION = {
    "product_version": "1.4.0",   # 来自 pyproject.toml
    "git_commit": "local-dev",     # CI 写入，本地兜底
    "build_time": "",              # CI 写入，本地兜底
    "branch": "local",             # CI 写入，本地兜底
}
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# 产品版本（真值来自 pyproject.toml）
# ---------------------------------------------------------------------------


def _get_product_version() -> str:
    # 项目约定从根目录启动，且当前目录只有一个 TOML 配置文件。
    toml_files = sorted(Path.cwd().glob("*.toml"))
    if toml_files:
        try:
            import tomllib  # Python 3.11+ 标准库

            with open(toml_files[0], "rb") as f:
                data = tomllib.load(f)
                return data["project"]["version"]
        except (KeyError, ImportError, OSError):
            pass
    return "unknown"


__version__ = _get_product_version()

# ---------------------------------------------------------------------------
# CI 生成的构建元信息（不要手动编辑这个文件）
# ---------------------------------------------------------------------------

BUILD_COMMIT = "local-dev"
BUILD_TIME = ""
BUILD_BRANCH = "local"

try:
    from ._build_info import BUILD_BRANCH, BUILD_COMMIT, BUILD_TIME
except ImportError:
    # 本地开发环境兜底，CI 打包时会覆盖
    pass

# ---------------------------------------------------------------------------
# 统一对外输出的完整版本对象，日志/接口都用这个
# ---------------------------------------------------------------------------

VERSION = {
    "product_version": __version__,
    "git_commit": BUILD_COMMIT,
    "build_time": BUILD_TIME,
    "branch": BUILD_BRANCH,
}
