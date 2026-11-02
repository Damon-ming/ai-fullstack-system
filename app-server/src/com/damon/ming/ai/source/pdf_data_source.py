# app-server/src/com/damon/ming/ai/source/pdf_data_source.py
"""
PDF 数据源 —— 路由层，线程编排由上层 RAGContainer 负责。

本模块只负责"给定 PDF 文件路径，返回 Document 列表"，
具体解析策略由 pdf/ 子包内的多策略解析器承担。
"""

import os
import threading
from pathlib import Path

from llama_index.core import Document
from src.com.damon.ming.ai.source import register_engine
from src.com.damon.ming.ai.source.base import BaseDataSource
from src.com.damon.ming.ai.source.pdf import route_pdf_parser
from src.com.damon.ming.log import pin


@register_engine("pdf")
class LocalPDFDataSource(BaseDataSource):
    """PDF 文件加载实现 —— 多策略路由。

    根据 PDF 特征自动选择解析策略：
      - 文本 PDF → pymupdf4llm 快速路径
      - 扫描件 PDF → PaddleOCR 路径

    新增解析策略只需在 pdf/__init__.py 的路由函数中追加规则，
    本类无需改动。
    """

    def __init__(
        self,
        folder_path: str,
        enable_image_extract: bool = False,
        vlm_model: str | None = None,
    ):
        self.folder_path = folder_path
        self.enable_image_extract = enable_image_extract
        self.vlm_model = vlm_model
        self.logger = pin("LocalPDFDataSource")
        self._ensure_dir_exists()
        self._images_dir = os.path.join(folder_path, "images")

        self._stats_lock = threading.Lock()
        self._stats = {
            "total_files": 0,
            "success_files": 0,
            "failed_files": 0,
            "total_pages": 0,
        }

    def _ensure_dir_exists(self) -> None:
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
            self.logger.info(f"[PDFDataSource] 创建知识库目录: {self.folder_path}")

    def _process_single_pdf(self, file_path: str) -> list[Document]:
        """处理单个 PDF —— 自动路由到对应解析器"""
        file_name = os.path.basename(file_path)

        try:
            parser = route_pdf_parser(
                file_path=file_path,
                images_dir=self._images_dir,
                enable_image_extract=self.enable_image_extract,
                vlm_model=self.vlm_model,
            )

            self.logger.debug(
                f"[PDFDataSource] 路由选择 | file={file_name} | "
                f"parser={type(parser).__name__}"
            )

            docs = parser.parse(file_path)

            with self._stats_lock:
                self._stats["success_files"] += 1
                self._stats["total_pages"] += sum(
                    d.metadata.get("total_pages", 1) for d in docs
                )

            return docs

        except Exception as e:
            with self._stats_lock:
                self._stats["failed_files"] += 1
            self.logger.exception(
                f"[PDFDataSource] 解析失败 | file={file_name} | error={e!s}"
            )
            return []

    def load_documents(self, reset_stats: bool = True) -> list[Document]:
        """加载目录下所有 PDF 文件（同步）"""
        self.logger.info(f"[PDFDataSource] 开始加载目录: {self.folder_path}")

        pdf_files = []
        for root, _, files in os.walk(self.folder_path):
            for file in files:
                if file.lower().endswith(".pdf"):
                    pdf_files.append(os.path.abspath(os.path.join(root, file)))

        if not pdf_files:
            self.logger.warning(
                f"[PDFDataSource] 目录中没有PDF文件: {self.folder_path}"
            )
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats["total_files"] = len(pdf_files)
                self._stats["success_files"] = 0
                self._stats["failed_files"] = 0
                self._stats["total_pages"] = 0

        self.logger.info(
            f"[PDFDataSource] 发现 {len(pdf_files)} 个PDF文件，逐个同步处理"
        )

        all_docs: list[Document] = []
        for file_path in pdf_files:
            docs = self._process_single_pdf(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[PDFDataSource] 加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总页数={self._stats['total_pages']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def load_specific_files(
        self, file_paths: list[str], reset_stats: bool = True
    ) -> list[Document]:
        """加载指定的一批 PDF 文件，用于增量上传（同步）"""
        self.logger.info(f"[PDFDataSource] 增量加载指定文件 count={len(file_paths)}")
        pdf_files = []
        for fp in file_paths:
            p = Path(fp).resolve()
            if p.exists() and p.suffix.lower() == ".pdf":
                pdf_files.append(str(p))
            else:
                self.logger.warning(f"[PDFDataSource] 跳过非PDF/不存在文件: {fp}")

        if not pdf_files:
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats["total_files"] = len(pdf_files)
                self._stats["success_files"] = 0
                self._stats["failed_files"] = 0
                self._stats["total_pages"] = 0

        all_docs: list[Document] = []
        for file_path in pdf_files:
            docs = self._process_single_pdf(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[PDFDataSource] 增量加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总页数={self._stats['total_pages']} | "
                f"总Document={len(all_docs)}"
            )
        return all_docs

    def get_stats(self) -> dict:
        """获取加载统计信息"""
        with self._stats_lock:
            return self._stats.copy()
