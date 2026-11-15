# app-server/src/com/damon/ming/security/digest.py
"""通用摘要工具。密码存储应使用 security.password_hasher。"""

import hashlib
from pathlib import Path


def sha256_hex(value: str | bytes) -> str:
    """计算文本或字节内容的 SHA-256 十六进制摘要。"""
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def sha256_file(file_path: str | Path, chunk_size: int = 1 << 20) -> str:
    """分块计算文件的 SHA-256 摘要，避免一次性读入整个文件。"""
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
