"""上传文件内容与文件扩展名的基础一致性校验。"""

from io import BytesIO
from zipfile import BadZipFile, ZipFile

_OFFICE_REQUIRED_ENTRIES = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}
_TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".html", ".htm"}


def validate_upload_content(suffix: str, content: bytes) -> None:
    """校验文件头/容器结构或文本可解码性，不替代对应格式解析器。"""
    if not content:
        raise ValueError("文件内容为空")

    if suffix == ".pdf":
        # PDF 头通常在文件开头；允许头部前存在少量兼容性字节。
        if b"%PDF-" not in content[:1024]:
            raise ValueError("PDF 文件头无效")
        return

    required_entry = _OFFICE_REQUIRED_ENTRIES.get(suffix)
    if required_entry:
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = archive.namelist()
                entries = set(names)
        except (BadZipFile, EOFError, OSError, ValueError):
            raise ValueError("Office 文件不是有效的 ZIP 容器") from None

        if (
            len(entries) != len(names)
            or "[Content_Types].xml" not in entries
            or required_entry not in entries
        ):
            raise ValueError("Office 文件内容与扩展名不匹配")
        return

    if suffix in _TEXT_EXTENSIONS:
        if b"\x00" in content:
            raise ValueError("文本文件包含 NUL 字节")
        for encoding in ("utf-8-sig", "gbk"):
            try:
                content.decode(encoding)
                return
            except UnicodeDecodeError:
                continue
        raise ValueError("文本文件编码无效")
