#!/usr/bin/env python3
"""Install the web-app pnpm workspace dependencies.

Usage:
    python scripts/install-frontend-deps.py

Requires Node.js and pnpm to be installed and available on PATH.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the web-app pnpm workspace dependencies"
    )
    parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    workspace = project_root / "web-app"
    required_files = (
        workspace / "package.json",
        workspace / "pnpm-lock.yaml",
        workspace / "pnpm-workspace.yaml",
    )
    missing_files = [path for path in required_files if not path.is_file()]
    if missing_files:
        print("前端 workspace 文件不完整：", file=sys.stderr)
        for path in missing_files:
            print(f"  - {path}", file=sys.stderr)
        return 2

    missing_tools = [name for name in ("node", "pnpm") if shutil.which(name) is None]
    if missing_tools:
        print(
            "缺少前置工具："
            + ", ".join(missing_tools)
            + "。请先安装 Node.js 和 pnpm，并确保它们在 PATH 中。",
            file=sys.stderr,
        )
        return 2

    print(f"在 {workspace} 安装前端 workspace 依赖（使用 pnpm-lock.yaml）…", flush=True)
    command = (
        "pnpm install --frozen-lockfile"
        if sys.platform == "win32"
        else [
            "pnpm",
            "install",
            "--frozen-lockfile",
        ]
    )
    try:
        result = subprocess.run(
            command, cwd=workspace, shell=sys.platform == "win32", check=False
        )
    except OSError as exc:
        print(f"无法启动 pnpm：{exc}", file=sys.stderr)
        return 2

    if result.returncode:
        print(f"前端依赖安装失败，退出码：{result.returncode}", file=sys.stderr)
        return result.returncode

    print("前端依赖安装完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
