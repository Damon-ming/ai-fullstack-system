# app-server/src/com/damon/ming/ai/source/markdown_data_source.py
"""
Markdown 数据源 —— 纯同步实现，线程编排由上层 RAGContainer 负责。

与纯文本数据源的核心差异：
  - 使用 LlamaIndex MarkdownNodeParser 做 AST 解析，
    按标题层级（## / ### / ####）切分 pre-chunk，
    保留标题路径作为 metadata（header_path）。
  - 超过 chunk_chars 的叶子节点按自然边界二次切分。

可配置项复用 SourceConfigLoader：
  - markdown_source.encoding_fallbacks: 编码尝试顺序
  - markdown_source.pre_chunk: 二次切分配置（边界优先级 + 块大小）
"""

import hashlib
import os
import threading
from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.config.source.source_config_loader import SourceConfigLoader
from src.com.damon.ming.ai.source import register_engine
from src.com.damon.ming.ai.source.base import BaseDataSource
from src.com.damon.ming.log import pin

logger = pin("LocalMarkdownDataSource")


@register_engine("md")
class LocalMarkdownDataSource(BaseDataSource):
    """Markdown 数据源，基于 AST 按标题层级预分块。"""

    def __init__(
        self,
        folder_path: str,
        encoding_fallbacks: tuple[str, ...] | None = None,
        pre_chunk_config=None,
    ):
        self.folder_path = folder_path
        self.logger = pin("LocalMarkdownDataSource")
        self._ensure_dir_exists()

        # 从 YAML 加载配置
        if encoding_fallbacks is None or pre_chunk_config is None:
            cfg = SourceConfigLoader().load()
            self._encoding_fallbacks = (
                encoding_fallbacks
                if encoding_fallbacks is not None
                else cfg.markdown_source.encoding_fallbacks
            )
            self._pre_chunk_config = (
                pre_chunk_config
                if pre_chunk_config is not None
                else cfg.markdown_source.pre_chunk
            )
        else:
            self._encoding_fallbacks = encoding_fallbacks
            self._pre_chunk_config = pre_chunk_config

        # AST 解析器（线程安全，可复用）
        self._parser = MarkdownNodeParser()

        # 实例级别锁
        self._stats_lock = threading.Lock()

        # 统计信息（线程安全）
        self._stats = {
            "total_files": 0,
            "success_files": 0,
            "failed_files": 0,
        }

    def _ensure_dir_exists(self) -> None:
        if not os.path.exists(self.folder_path):
            os.makedirs(self.folder_path)
            self.logger.info(f"[MarkdownDataSource] 创建知识库目录: {self.folder_path}")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _read_text(self, file_path: str) -> str:
        """读取文件，按配置编码顺序尝试。"""
        for encoding in self._encoding_fallbacks:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _pre_chunk_text(self, text: str) -> list[tuple[str, dict]]:
        """基于 AST 按标题层级预分块。

        Returns:
            [(chunk_text, header_metadata), ...]
            header_metadata 包含 header_path 等信息。
        """
        doc = Document(text=text)
        nodes: list[TextNode] = self._parser.get_nodes_from_documents([doc])

        chunks: list[tuple[str, dict]] = []
        cfg = self._pre_chunk_config

        for node in nodes:
            node_text = node.text.strip()
            if not node_text:
                continue

            header_meta = dict(node.metadata) if node.metadata else {}

            # 未超限，整体作为一个 chunk
            if len(node_text) <= cfg.chunk_chars:
                chunks.append((node_text, header_meta))
                continue

            # 超限，按自然边界二次切分
            sub_chunks = self._split_by_boundaries(node_text)
            for i, sub in enumerate(sub_chunks):
                chunks.append((sub, header_meta))

        # 无子标题时整个文档作为一个 chunk
        if not chunks:
            chunks.append((text, {}))

        return chunks

    def _split_by_boundaries(self, text: str) -> list[str]:
        """按自然边界二次切分超大段落。"""
        cfg = self._pre_chunk_config
        chunk_size = cfg.chunk_chars
        boundaries = cfg.boundaries

        chunks = []
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

    def _find_split_pos(
        self, text: str, start: int, end: int, boundaries: tuple[str, ...]
    ) -> int:
        """在 [start, end] 范围内找最佳切分点。"""
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
        """处理单个 Markdown 文件"""
        file_name = os.path.basename(file_path)

        try:
            file_sha256 = self._get_file_sha256(file_path)
            text = self._read_text(file_path)
            text_stripped = text.strip()

            if not text_stripped:
                self.logger.warning(f"[MarkdownDataSource] 空文件: {file_name}")
                return []

            # AST 解析 + 预分块
            chunks_with_meta = self._pre_chunk_text(text_stripped)

            docs = []
            for idx, (chunk_text, header_meta) in enumerate(chunks_with_meta):
                doc = Document(
                    text=chunk_text,
                    metadata={
                        "file_name": file_name,
                        "file_path": file_path,
                        "file_sha256": file_sha256,
                        "source_refId": file_sha256,
                        "page": 1,
                        "page_index": 0,
                        "total_pages": 1,
                        "pre_chunk_index": idx,
                        "pre_chunk_total": len(chunks_with_meta),
                        **header_meta,
                    },
                )
                docs.append(doc)

            with self._stats_lock:
                self._stats["success_files"] += 1

            self.logger.info(
                f"[MarkdownDataSource] 读取成功 | file={file_name} | "
                f"sections={len(chunks_with_meta)} | sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            with self._stats_lock:
                self._stats["failed_files"] += 1

            self.logger.exception(
                f"[MarkdownDataSource] 读取失败 | file={file_name} | error={e!s}",
            )
            return []

    def load_documents(self, reset_stats: bool = True) -> list[Document]:
        """加载目录下所有 Markdown 文件（同步）"""
        self.logger.info(f"[MarkdownDataSource] 开始加载目录: {self.folder_path}")

        md_files = []
        for root, _, files in os.walk(self.folder_path):
            for fname in files:
                if fname.lower().endswith(".md"):
                    md_files.append(os.path.abspath(os.path.join(root, fname)))

        if not md_files:
            self.logger.warning(
                f"[MarkdownDataSource] 目录中没有 Markdown 文件: {self.folder_path}"
            )
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats["total_files"] = len(md_files)
                self._stats["success_files"] = 0
                self._stats["failed_files"] = 0

        all_docs = []
        for file_path in md_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[MarkdownDataSource] 加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def load_specific_files(
        self, file_paths: list[str], reset_stats: bool = True
    ) -> list[Document]:
        """加载指定的 Markdown 文件列表，用于增量上传（同步）"""
        self.logger.info(
            f"[MarkdownDataSource] 增量加载指定文件 count={len(file_paths)}"
        )
        md_files = []
        for fp in file_paths:
            p = Path(fp).resolve()
            if p.exists() and p.suffix.lower() == ".md":
                md_files.append(str(p))
            else:
                self.logger.warning(f"[MarkdownDataSource] 跳过非MD/不存在文件: {fp}")

        if not md_files:
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats["total_files"] = len(md_files)
                self._stats["success_files"] = 0
                self._stats["failed_files"] = 0

        all_docs = []
        for file_path in md_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[MarkdownDataSource] 增量加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def get_stats(self) -> dict:
        """获取加载统计信息"""
        with self._stats_lock:
            return self._stats.copy()
