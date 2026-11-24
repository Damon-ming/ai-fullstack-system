"""上传文件内容与文件扩展名的基础一致性校验。"""

from io import BytesIO
from zipfile import BadZipFile, ZipFile

_OFFICE_REQUIRED_ENTRIES = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}
_TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".html", ".htm"}
_LEGACY_OFFICE_EXTENSIONS = {".doc", ".ppt", ".xls"}
_LEGACY_OFFICE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_IMAGE_SIGNATURES = {
    ".bmp": (b"BM",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".jpg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".tif": (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"),
    ".tiff": (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"),
}


def validate_upload_content(suffix: str, content: bytes) -> None:
    """校验文件头/容器结构或文本可解码性，不替代对应格式解析器。"""
    if not content:
        raise ValueError("文件内容为空")

    if suffix == ".pdf":
        # PDF 头通常在文件开头；允许头部前存在少量兼容性字节。
        if b"%PDF-" not in content[:1024]:
            raise ValueError("PDF 文件头无效")
        return

    if suffix in _LEGACY_OFFICE_EXTENSIONS:
        is_rtf_word_document = suffix == ".doc" and content.lstrip().startswith(
            b"{\\rtf"
        )
        if (
            not content.startswith(_LEGACY_OFFICE_SIGNATURE)
            and not is_rtf_word_document
        ):
            raise ValueError("旧版 Office 文件头无效")
        return

    image_signatures = _IMAGE_SIGNATURES.get(suffix)
    if image_signatures:
        if not any(content.startswith(signature) for signature in image_signatures):
            raise ValueError("图片文件内容与扩展名不匹配")
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
