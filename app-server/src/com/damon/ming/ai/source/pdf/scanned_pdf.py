# app-server/src/com/damon/ming/ai/source/pdf/scanned_pdf.py
"""
扫描件 PDF 解析器 —— 基于 PaddleOCR 的图像路径。

适用于：纯图片扫描件（无可选中字层）。
策略：fitz 逐页提取图片 → PaddleOCR 识别文字 → Document。
"""

import hashlib
import os
from pathlib import Path

import fitz  # pymupdf
from llama_index.core import Document
from src.com.damon.ming.ai.source.image_text_extractor import extract_image_text
from src.com.damon.ming.log import pin

from .base_pdf import BasePdfParser


class ScannedPdfParser(BasePdfParser):
    """扫描件 PDF 解析器。"""

    def __init__(
        self,
        images_dir: str,
        vlm_model: str | None = None,
    ):
        self.images_dir = images_dir
        self.vlm_model = vlm_model
        self.logger = pin("ScannedPdfParser")

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
            doc = fitz.open(file_path)
            total_page_count = doc.page_count
            docs: list[Document] = []

            for page_idx in range(total_page_count):
                page = doc[page_idx]
                page_no = page_idx + 1
                image_paths: list[str] = []
                page_text_parts: list[str] = []

                images = page.get_images(full=True)
                for img_idx, img_info in enumerate(images):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    image_bytes = base_image["image"]
                    ext = base_image.get("ext", "png")
                    pdf_name = Path(file_path).stem
                    image_filename = f"{pdf_name}_page{page_no}_img{img_idx + 1}.{ext}"
                    image_path = str(Path(self.images_dir) / image_filename)
                    Path(self.images_dir).mkdir(parents=True, exist_ok=True)

                    with open(image_path, "wb") as f:
                        f.write(image_bytes)

                    img_text = extract_image_text(image_path, self.vlm_model)
                    if img_text:
                        page_text_parts.append(img_text)
                    image_paths.append(image_path)

                full_text = "\n".join(page_text_parts).strip()

                page_doc = Document(
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
                        "parse_method": "ocr",
                    },
                )
                docs.append(page_doc)

            doc.close()

            self.logger.info(
                f"[ScannedPdf] 解析成功 | file={file_name} | "
                f"pages={total_page_count} | sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            self.logger.exception(
                f"[ScannedPdf] 解析失败 | file={file_name} | error={e!s}"
            )
            return []
