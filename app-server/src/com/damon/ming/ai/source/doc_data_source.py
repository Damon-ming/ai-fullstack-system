# app-server/src/com/damon/ming/ai/source/doc_data_source.py
"""
DOC/DOCX 数据源 —— 纯同步实现，线程编排由上层 RAGContainer 负责。

使用 python-docx 提取 .docx 文件的文本和表格内容。
旧版 .doc（BIFF 格式）无法直接读取，需先转换为 .docx。

工业级特性：
  - 标题感知：识别 Heading 1~9 样式，保留层级信息
  - 表格提取：将 Word 表格格式化为 Markdown 表格
  - 预分块：超大文本段落按自然边界（\\n\\n → \\n → 字符级）切分
  - 可配置：块大小、边界优先级、是否包含表格

可配置项通过 SourceConfigLoader 从 YAML 读取：
  - doc_source.pre_chunk: 预分块配置（边界优先级 + 块大小）
  - doc_source.include_tables: 是否提取表格为 Markdown 表格

page 语义：按 page break 分页，超大段落二次切分后 page_index 递增。
"""

import hashlib
import os
import re
import threading
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocumentType
from llama_index.core import Document
from src.com.damon.ming.ai.config.source.source_config_loader import SourceConfigLoader
from src.com.damon.ming.ai.source import register_engine
from src.com.damon.ming.ai.source.base import BaseDataSource
from src.com.damon.ming.log import pin

logger = pin("LocalDocDataSource")

# 匹配 Word 内置标题样式的正则：Heading 1 ~ Heading 9
_HEADING_PATTERN = re.compile(r"^Heading\s+(\d+)$", re.IGNORECASE)


@register_engine("doc")
class LocalDocDataSource(BaseDataSource):
    """DOC/DOCX 文件加载实现，同步处理。

    上层 RAGContainer 使用 asyncio.to_thread 或 ThreadPoolExecutor
    将本类的调用提交到线程池，本类不感知线程环境。
    """

    def __init__(
        self,
        folder_path: str,
        pre_chunk_config=None,
        include_tables: bool | None = None,
    ):
        self.folder_path = folder_path
        self.logger = pin("LocalDocDataSource")
        self._ensure_dir_exists()

        cfg = SourceConfigLoader().load()
        self._pre_chunk_config = (
            pre_chunk_config
            if pre_chunk_config is not None
            else cfg.doc_source.pre_chunk
        )
        self._include_tables = (
            include_tables
            if include_tables is not None
            else cfg.doc_source.include_tables
        )

        # 实例级别锁
        self._stats_lock = threading.Lock()

        # 统计信息（线程安全）
        self._stats = {
            "total_files": 0,
            "success_files": 0,
            "failed_files": 0,
            "total_pages": 0,
            "total_tables": 0,
        }

    def _ensure_dir_exists(self) -> None:
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
            self.logger.info(f"[DocDataSource] 创建知识库目录: {self.folder_path}")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _extract_paragraphs(
        self, doc: DocxDocumentType
    ) -> list[tuple[str, int | None]]:
        """提取段落文本和标题层级。

        Returns:
            list of (text, heading_level)
            heading_level 为 None 表示普通段落，1-9 表示标题层级。
        """
        results: list[tuple[str, int | None]] = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # 检测标题样式
            heading_level = None
            style_name = para.style.name if para.style else ""
            match = _HEADING_PATTERN.match(style_name)
            if match:
                heading_level = int(match.group(1))

            results.append((text, heading_level))

        return results

    @staticmethod
    def _extract_tables(doc: DocxDocumentType) -> list[str]:
        """将 Word 表格格式化为 Markdown 表格文本。"""
        tables: list[str] = []
        for table in doc.tables:
            if not table.rows:
                continue

            rows: list[list[str]] = []
            for row in table.rows:
                cells = [cell.text.strip().replace("|", "\\|") for cell in row.cells]
                rows.append(cells)

            if not rows:
                continue

            col_count = max(len(r) for r in rows)
            # 补齐列数
            for r in rows:
                while len(r) < col_count:
                    r.append("")

            lines = []
            # 表头
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("| " + " | ".join(["---"] * col_count) + " |")
            # 数据行
            for row in rows[1:]:
                lines.append("| " + " | ".join(row) + " |")

            tables.append("\n".join(lines))

        return tables

    @staticmethod
    def _find_page_break_runs(doc: DocxDocumentType) -> set[int]:
        """找到所有包含 page break 的段落索引。"""
        break_indices: set[int] = set()
        for idx, para in enumerate(doc.paragraphs):
            for run in para.runs:
                if 'w:type="page"' in run._element.xml:
                    break_indices.add(idx)
                    break
        return break_indices

    def _pre_chunk_text(self, text: str) -> list[str]:
        """按配置的自然边界优先级预分块。

        策略：按边界优先级依次尝试，找到第一个能切分的边界就切；
        空字符串 "" 作为兜底表示按固定长度硬切。
        """
        cfg = self._pre_chunk_config
        if not cfg.enabled or len(text) <= cfg.chunk_chars:
            return [text]

        chunk_size = cfg.chunk_chars
        boundaries = cfg.boundaries

        chunks: list[str] = []
        pos = 0
        text_len = len(text)

        while pos < text_len:
            end = min(pos + chunk_size, text_len)

            if end < text_len:
                split_pos = self._find_split_pos(text, pos, end, boundaries)
                end = split_pos

            chunks.append(text[pos:end])

            if end >= text_len:
                break

            pos = end

        return [c for c in chunks if c.strip()]

    @staticmethod
    def _find_split_pos(
        text: str, start: int, end: int, boundaries: tuple[str, ...]
    ) -> int:
        """在 [start, end] 范围内找最佳切分点。

        搜索范围限定在后半区 [mid, end]，保证块大小不过小。
        按边界优先级依次尝试，返回找到的最右切分点 + 1。
        """
        mid = start + (end - start) // 2

        for sep in boundaries:
            if sep == "":
                return end

            search_region = text[mid:end]
            last_idx = search_region.rfind(sep)
            if last_idx != -1:
                return mid + last_idx + len(sep)

        return end

    def _process_single_file(self, file_path: str) -> list[Document]:
        """处理单个 DOC/DOCX 文件"""
        file_name = os.path.basename(file_path)
        suffix = Path(file_path).suffix.lower()

        try:
            file_sha256 = self._get_file_sha256(file_path)

            if suffix == ".doc":
                self.logger.warning(
                    f"[DocDataSource] 跳过旧版 .doc 文件（请先转为 .docx）: {file_name}"
                )
                return []

            doc = Document(file_path)
            paragraphs = self._extract_paragraphs(doc)
            page_break_indices = self._find_page_break_runs(doc)

            if not paragraphs:
                self.logger.warning(f"[DocDataSource] 空文档: {file_name}")
                return []

            # ── 按 page break 分组 ──────────────────────────────────
            pages: list[list[tuple[str, int | None]]] = []
            current_page: list[tuple[str, int | None]] = []

            for idx, (text, level) in enumerate(paragraphs):
                current_page.append((text, level))
                if idx in page_break_indices:
                    pages.append(current_page)
                    current_page = []

            if current_page:
                pages.append(current_page)

            # 无 page break 时整文档为一页
            if not pages:
                pages = [paragraphs]

            # ── 提取表格 ────────────────────────────────────────────
            table_texts: list[str] = []
            if self._include_tables:
                table_texts = self._extract_tables(doc)

            # ── 构建 Document 列表 ──────────────────────────────────
            docs: list[Document] = []
            global_page_index = 0

            for page_paras in pages:
                # 合并页面内所有段落
                page_text = "\n".join(t for t, _ in page_paras)
                if not page_text.strip():
                    continue

                # 检测页面内最高标题层级
                heading_levels = [l for _, l in page_paras if l is not None]
                min_heading = min(heading_levels) if heading_levels else None

                # 二次预分块（超大段落）
                sub_texts = self._pre_chunk_text(page_text.strip())

                for chunk_text in sub_texts:
                    doc = Document(
                        text=chunk_text,
                        metadata={
                            "file_name": file_name,
                            "file_path": file_path,
                            "file_sha256": file_sha256,
                            "source_refId": file_sha256,
                            "page": global_page_index + 1,
                            "page_index": global_page_index,
                            "heading_level": min_heading,
                        },
                    )
                    docs.append(doc)
                    global_page_index += 1

            # 表格作为独立 Document
            for table_text in table_texts:
                doc = Document(
                    text=table_text,
                    metadata={
                        "file_name": file_name,
                        "file_path": file_path,
                        "file_sha256": file_sha256,
                        "source_refId": file_sha256,
                        "page": global_page_index + 1,
                        "page_index": global_page_index,
                        "content_type": "table",
                    },
                )
                docs.append(doc)
                global_page_index += 1

            total_pages = global_page_index
            # 回填 total_pages
            for doc in docs:
                doc.metadata["total_pages"] = total_pages

            # 更新统计
            with self._stats_lock:
                self._stats["success_files"] += 1
                self._stats["total_pages"] += total_pages
                self._stats["total_tables"] += len(table_texts)

            self.logger.info(
                f"[DocDataSource] 读取成功 | file={file_name} | "
                f"pages={total_pages} | tables={len(table_texts)} | "
                f"sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            with self._stats_lock:
                self._stats["failed_files"] += 1

            self.logger.exception(
                f"[DocDataSource] 读取失败 | file={file_name} | error={e!s}",
            )
            return []

    def load_documents(self, reset_stats: bool = True) -> list[Document]:
        """加载目录下所有 DOC/DOCX 文件（同步）"""
        self.logger.info(f"[DocDataSource] 开始加载目录: {self.folder_path}")

        doc_files = []
        for root, _, files in os.walk(self.folder_path):
            for fname in files:
                if fname.lower().endswith((".docx", ".doc")):
                    doc_files.append(os.path.abspath(os.path.join(root, fname)))

        if not doc_files:
            self.logger.warning(
                f"[DocDataSource] 目录中没有 DOC/DOCX 文件: {self.folder_path}"
            )
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats = {
                    "total_files": len(doc_files),
                    "success_files": 0,
                    "failed_files": 0,
                    "total_pages": 0,
                    "total_tables": 0,
                }

        all_docs = []
        for file_path in doc_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[DocDataSource] 加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总页数={self._stats['total_pages']} | "
                f"总表格={self._stats['total_tables']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def load_specific_files(
        self, file_paths: list[str], reset_stats: bool = True
    ) -> list[Document]:
        """加载指定的 DOC/DOCX 文件列表，用于增量上传（同步）"""
        self.logger.info(f"[DocDataSource] 增量加载指定文件 count={len(file_paths)}")

        doc_files = []
        for fp in file_paths:
            p = Path(fp).resolve()
            if p.exists() and p.suffix.lower() in (".docx", ".doc"):
                doc_files.append(str(p))
            else:
                self.logger.warning(f"[DocDataSource] 跳过非DOC/不存在文件: {fp}")

        if not doc_files:
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats = {
                    "total_files": len(doc_files),
                    "success_files": 0,
                    "failed_files": 0,
                    "total_pages": 0,
                    "total_tables": 0,
                }

        all_docs = []
        for file_path in doc_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[DocDataSource] 增量加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总页数={self._stats['total_pages']} | "
                f"总表格={self._stats['total_tables']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def get_stats(self) -> dict:
        """获取加载统计信息"""
        with self._stats_lock:
            return self._stats.copy()
