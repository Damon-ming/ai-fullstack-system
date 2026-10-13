# app-server/src/com/damon/ming/version.py
"""
版本信息 —— 单一版本源 + CI 构建元信息。

产品版本真值唯一来源：../pyproject.toml（与 Dockerfile 同级）
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
    # 文件位置：src/com/damon/ming/version.py → 上五级 = 项目根目录（app-server/）
    #   version.py → ming/ → damon/ → com/ → src/ → app-server/
    pyproject_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent / "pyproject.toml"
    )
    if pyproject_path.exists():
        try:
            import tomllib  # Python 3.11+ 标准库

            with open(pyproject_path, "rb") as f:
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
