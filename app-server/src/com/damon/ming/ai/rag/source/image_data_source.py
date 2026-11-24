"""独立图片数据源：对图片执行 OCR 并生成可检索文档。"""

import os
from pathlib import Path

from llama_index.core import Document
from src.com.damon.ming.ai.rag.knowledge.metadata_keys import (
    CONTENT_TYPE,
    FILE_NAME,
    FILE_PATH,
    FILE_SHA256,
    PAGE,
    PAGE_INDEX,
    SOURCE_REF_ID,
    TOTAL_PAGES,
)
from src.com.damon.ming.ai.rag.source import register_engine
from src.com.damon.ming.ai.rag.source.base import BaseDataSource
from src.com.damon.ming.ai.rag.source.image_text_extractor import extract_image_text
from src.com.damon.ming.log import pin
from src.com.damon.ming.security.digest import sha256_file

logger = pin("LocalImageDataSource")


@register_engine("image")
class LocalImageDataSource(BaseDataSource):
    """使用项目现有 OCR 提取独立图片中的文字。"""

    def __init__(self, folder_path: str, supported_extensions: set[str]) -> None:
        super().__init__(folder_path)
        self._supported_extensions = supported_extensions

    def load_documents(self) -> list[Document]:
        """加载图片目录中的受支持图片。"""
        image_paths = [
            str(Path(root) / file_name)
            for root, _, file_names in os.walk(self.folder_path)
            for file_name in file_names
            if Path(file_name).suffix.lower() in self._supported_extensions
        ]
        return self.load_specific_files(image_paths)

    def load_specific_files(self, file_paths: list[str]) -> list[Document]:
        """解析指定图片；没有识别出文字的图片不创建空文档。"""
        documents: list[Document] = []
        for file_path in file_paths:
            path = Path(file_path).resolve()
            if (
                not path.is_file()
                or path.suffix.lower() not in self._supported_extensions
            ):
                logger.warning(f"[ImageDataSource] 跳过非图片/不存在文件: {file_path}")
                continue

            try:
                extracted_text = extract_image_text(str(path)).strip()
                if not extracted_text:
                    logger.warning(
                        f"[ImageDataSource] 图片未识别出文字，跳过: {path.name}"
                    )
                    continue

                file_sha256 = sha256_file(str(path))
                documents.append(
                    Document(
                        text=extracted_text,
                        metadata={
                            FILE_NAME: path.name,
                            FILE_PATH: str(path),
                            FILE_SHA256: file_sha256,
                            SOURCE_REF_ID: file_sha256,
                            PAGE: 1,
                            PAGE_INDEX: 0,
                            TOTAL_PAGES: 1,
                            CONTENT_TYPE: "image_text",
                        },
                    )
                )
                logger.info(f"[ImageDataSource] 图片 OCR 完成: {path.name}")
            except Exception:
                logger.exception(f"[ImageDataSource] 图片解析失败: {path}")

        return documents
