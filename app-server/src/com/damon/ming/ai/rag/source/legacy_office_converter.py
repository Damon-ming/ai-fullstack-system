# app-server/src/com/damon/ming/ai/rag/source/legacy_office_converter.py
"""将旧版 Office 文件转换为现有解析器支持的 OOXML 格式。"""

import shutil
import subprocess  # nosec B404 - LibreOffice conversion requires a child process.
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

LEGACY_OFFICE_TARGETS = {
    ".doc": ".docx",
    ".ppt": ".pptx",
    ".xls": ".xlsx",
}
LEGACY_OFFICE_EXTENSIONS = frozenset(LEGACY_OFFICE_TARGETS)


@contextmanager
def convert_legacy_office(
    file_path: str | Path,
    timeout_seconds: int,
) -> Generator[Path, None, None]:
    """转换单个旧版 Office 文件，并在退出时清理临时产物。"""
    source_path = Path(file_path).resolve()
    target_suffix = LEGACY_OFFICE_TARGETS.get(source_path.suffix.lower())
    if target_suffix is None:
        raise ValueError(f"不支持转换的旧版 Office 格式: {source_path.suffix}")
    if not source_path.is_file():
        raise FileNotFoundError(f"旧版 Office 文件不存在: {source_path}")

    soffice = shutil.which("soffice") or shutil.which("soffice.exe")
    if soffice is None:
        raise FileNotFoundError(
            "未找到 LibreOffice 命令 soffice，无法转换旧版 Office 文件"
        )

    with tempfile.TemporaryDirectory(prefix="legacy-office-") as temporary_dir:
        temporary_path = Path(temporary_dir)
        output_dir = temporary_path / "output"
        profile_dir = temporary_path / "profile"
        output_dir.mkdir()
        profile_dir.mkdir()
        converted_path = output_dir / f"{source_path.stem}{target_suffix}"
        profile_uri = profile_dir.resolve().as_uri()
        command = [
            soffice,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to",
            target_suffix.lstrip("."),
            "--outdir",
            str(output_dir),
            str(source_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                shell=False,
            )  # nosec B603 - fixed executable/options; file path is one argv item, never shell-interpreted.
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(
                f"旧版 Office 转换超时（{timeout_seconds} 秒）: {source_path.name}"
            ) from error

        if result.returncode != 0 or not converted_path.is_file():
            details = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                f"旧版 Office 转换失败: {source_path.name}"
                + (f" | {details}" if details else "")
            )

        yield converted_path
