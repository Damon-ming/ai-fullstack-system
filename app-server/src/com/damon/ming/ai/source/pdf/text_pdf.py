# app-server/src/com/damon/ming/ai/source/pdf/text_pdf.py
"""
文本型 PDF 解析器 —— 基于 pymupdf4llm 的快速路径。

适用于：可复制文字的数字 PDF（有可选中文字层）。
策略：pymupdf4llm → markdown 文本 + 图片提取 OCR → Document。
"""

import hashlib
import os

import pymupdf4llm
from llama_index.core import Document
from src.com.damon.ming.ai.source.image_text_extractor import (
    extract_image_text,
    extract_images_from_pdf_page,
)
from src.com.damon.ming.log import pin

from .base_pdf import BasePdfParser


class TextPdfParser(BasePdfParser):
    """文本 PDF 解析器。"""

    def __init__(
        self,
        images_dir: str,
        enable_image_extract: bool = False,
        vlm_model: str | None = None,
    ):
        self.images_dir = images_dir
        self.enable_image_extract = enable_image_extract
        self.vlm_model = vlm_model
        self.logger = pin("TextPdfParser")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def parse(self, file_path: str) -> list[Document]:
        file_name = os.path.basename(file_path)
        try:
            file_sha256 = self._get_file_sha256(file_path)
            md_pages = pymupdf4llm.to_markdown(
                file_path,
                page_chunks=True,
                write_images=False,
                dpi=150,
            )
            total_page_count = len(md_pages)
            docs: list[Document] = []

            for page_item in md_pages:
                page_idx = page_item.get("page")
                if page_idx is not None:
                    page_no = page_idx + 1
                else:
                    meta = page_item.get("metadata", {})
                    page_idx = meta.get("page_number", -1)
                    page_no = page_idx
                    if page_idx == -1:
                        self.logger.warning(f"无法解析页码: {page_item}")

                page_text = page_item.get("text", "")

                # 图片提取 + OCR
                image_text = ""
                image_paths: list[str] = []
                if self.enable_image_extract:
                    page_images = extract_images_from_pdf_page(
                        file_path, page_idx, self.images_dir
                    )
                    for img_path in page_images:
                        img_text = extract_image_text(img_path, self.vlm_model)
                        if img_text:
                            image_text += f"\n{img_text}"
                        image_paths.append(img_path)

                full_text = (page_text + image_text).strip()

                doc = Document(
                    text=full_text,
                    metadata={
                        "file_name": file_name,
                        "file_path": file_path,
                        "file_sha256": file_sha256,
                        "source_refId": file_sha256,
                        "page": page_no,
                        "page_index": page_idx,
                        "total_pages": total_page_count,
                        "images": image_paths,
                        "parse_method": "text",
                    },
                )
                docs.append(doc)

            self.logger.info(
                f"[TextPdf] 解析成功 | file={file_name} | "
                f"pages={total_page_count} | sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            self.logger.exception(
                f"[TextPdf] 解析失败 | file={file_name} | error={e!s}"
            )
            return []
