# app-server/src/com/damon/ming/ai/source/ref_sources.py
import hashlib
import os
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pymupdf4llm
from llama_index.core import Document
from src.com.damon.ming.log import pin


class BaseDataSource(ABC):
    """数据源抽象：仅负责加载原始文档"""

    @abstractmethod
    def load_documents(self) -> list[Document]:
        pass

    @abstractmethod
    def load_specific_files(self, file_paths: list[str]) -> list[Document]:
        pass


class LocalPDFDataSource(BaseDataSource):
    """PDF文件加载实现，支持并发加载"""

    # 类级别锁，用于统计信息同步
    _stats_lock = threading.Lock()

    def __init__(
        self,
        folder_path: str,
        enable_image_extract: bool = False,
        max_workers: int | None = None,
    ):
        self.folder_path = folder_path
        self.enable_image_extract = enable_image_extract
        # 默认使用CPU核心数*2作为线程数
        self.max_workers = max_workers or min(os.cpu_count() * 2, 8)
        self.logger = pin("LocalPDFDataSource")
        self._ensure_dir_exists()

        # 统计信息（线程安全）
        self._stats = {
            "total_files": 0,
            "success_files": 0,
            "failed_files": 0,
            "total_pages": 0,
        }

    def _ensure_dir_exists(self):
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
            self.logger.info(f"[PDFDataSource] 创建知识库目录: {self.folder_path}")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _process_single_pdf(self, file_path: str) -> list[Document]:
        """处理单个PDF文件（线程安全）"""
        file_name = os.path.basename(file_path)

        try:
            file_md5 = self._get_file_sha256(file_path)
            md_pages = pymupdf4llm.to_markdown(
                file_path,
                page_chunks=True,
                write_images=self.enable_image_extract,
                dpi=150,
            )

            total_page_count = len(md_pages)
            docs = []

            for page_item in md_pages:
                page_idx = page_item.get("page")
                if page_idx is not None:
                    # 外层page存在：0起始，+1转为展示页码
                    page_no = page_idx + 1
                else:
                    # 外层page不存在，从metadata读取（1起始，不需要+1）
                    meta = page_item.get("metadata", {})
                    page_idx = meta.get("page_number", -1)
                    page_no = page_idx
                    if page_idx == -1:
                        self.logger.warning(
                            f"当前PDF块无法解析页码，原始数据：{page_item}"
                        )

                page_text = page_item["text"]

                doc = Document(
                    text=page_text.strip(),
                    metadata={
                        "file_name": file_name,
                        "file_path": file_path,
                        "file_md5": file_md5,
                        "source_refId": file_md5,
                        "page": page_no,
                        "page_index": page_idx,
                        "total_pages": total_page_count,
                    },
                )
                docs.append(doc)

            # 更新统计（线程安全）
            with self._stats_lock:
                self._stats["success_files"] += 1
                self._stats["total_pages"] += total_page_count

            self.logger.info(
                f"[PDFDataSource] 解析成功 | file={file_name} | "
                f"pages={total_page_count} | md5={file_md5[:8]}..."
            )
            return docs

        except Exception as e:
            # 更新失败统计（线程安全）
            with self._stats_lock:
                self._stats["failed_files"] += 1

            self.logger.error(
                f"[PDFDataSource] 解析失败 | file={file_name} | error={e!s}",
                exc_info=True,
            )
            return []

    def load_documents(self) -> list[Document]:
        """加载所有文档（使用线程池并发）"""
        self.logger.info(f"[PDFDataSource] 开始加载目录: {self.folder_path}")

        # 收集所有文件
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

        # 重置统计
        with self._stats_lock:
            self._stats["total_files"] = len(pdf_files)
            self._stats["success_files"] = 0
            self._stats["failed_files"] = 0
            self._stats["total_pages"] = 0

        self.logger.info(
            f"[PDFDataSource] 发现 {len(pdf_files)} 个PDF文件，使用 {self.max_workers} 个线程并发处理"
        )

        all_docs = []

        # 使用线程池并发处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_file = {
                executor.submit(self._process_single_pdf, file_path): file_path
                for file_path in pdf_files
            }

            # 收集结果（按完成顺序）
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    docs = future.result(timeout=300)  # 5分钟超时
                    all_docs.extend(docs)
                except Exception as e:
                    self.logger.error(
                        f"[PDFDataSource] 处理文件异常 | file={file_path} | error={e}"
                    )
                    with self._stats_lock:
                        self._stats["failed_files"] += 1

        # 输出最终统计
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

    def load_specific_files(self, file_paths: list[str]) -> list[Document]:
        """只加载指定的一批PDF文件，用于增量上传，不扫描整个知识库目录"""
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

        # 重置统计
        with self._stats_lock:
            self._stats["total_files"] = len(pdf_files)
            self._stats["success_files"] = 0
            self._stats["failed_files"] = 0
            self._stats["total_pages"] = 0

        all_docs = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self._process_single_pdf, file_path): file_path
                for file_path in pdf_files
            }
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    docs = future.result(timeout=300)
                    all_docs.extend(docs)
                except Exception as e:
                    self.logger.error(
                        f"[PDFDataSource] 增量处理文件异常 | file={file_path} | error={e}"
                    )
                    with self._stats_lock:
                        self._stats["failed_files"] += 1

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
