# app-server/src/com/damon/ming/ai/source/text_data_source.py
"""
纯文本 / Markdown 数据源 —— 纯同步实现，线程编排由上层 RAGContainer 负责。

本模块只负责"给定文本文件路径，返回 Document 列表"，
不感知线程池、取消令牌等基础设施。

大文件预分块：入库前按自然边界（段落→换行→字符级兜底）切成多个 Document，
使每个 Document 粒度合理，匹配 PDF 按标题切章节的效果，
避免检索时章节重建拉回全文。

可配置项通过 SourceConfigLoader 从 YAML 读取：
  - text_source.extensions: 文本数据源支持的文件扩展名
  - text_source.encoding_fallbacks: 编码尝试顺序
  - text_source.pre_chunk: 预分块配置（边界优先级 + 块大小 + 重叠）
"""

import hashlib
import os
import threading
from pathlib import Path

from llama_index.core import Document
from src.com.damon.ming.ai.config.source.source_config_loader import SourceConfigLoader
from src.com.damon.ming.log import pin

logger = pin("LocalTextDataSource")


class LocalTextDataSource:
    """纯文本 / Markdown 数据源，同步处理。

    上层 RAGContainer 使用 asyncio.to_thread 或 ThreadPoolExecutor
    将本类的调用提交到线程池，本类不感知线程环境。
    """

    def __init__(
        self,
        folder_path: str,
        supported_extensions: set[str] | None = None,
        encoding_fallbacks: tuple[str, ...] | None = None,
        pre_chunk_config=None,
    ):
        self.folder_path = folder_path
        self.logger = pin("LocalTextDataSource")
        self._ensure_dir_exists()

        # 从 YAML 加载配置（未提供参数时使用配置值）
        if (
            supported_extensions is None
            or encoding_fallbacks is None
            or pre_chunk_config is None
        ):
            cfg = SourceConfigLoader().load()
            self._supported_extensions = (
                supported_extensions
                if supported_extensions is not None
                else cfg.text_source.extensions
            )
            self._encoding_fallbacks = (
                encoding_fallbacks
                if encoding_fallbacks is not None
                else cfg.text_source.encoding_fallbacks
            )
            self._pre_chunk_config = (
                pre_chunk_config
                if pre_chunk_config is not None
                else cfg.text_source.pre_chunk
            )
        else:
            self._supported_extensions = supported_extensions
            self._encoding_fallbacks = encoding_fallbacks
            self._pre_chunk_config = pre_chunk_config

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
            self.logger.info(f"[TextDataSource] 创建知识库目录: {self.folder_path}")

    @staticmethod
    def _get_file_sha256(file_path: str) -> str:
        hash_sha256 = hashlib.sha256()
        buffer_size = 8192
        with open(file_path, "rb") as f:
            while chunk := f.read(buffer_size):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _read_text(self, file_path: str) -> str:
        """读取文本文件，按配置编码顺序尝试。"""
        for encoding in self._encoding_fallbacks:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        # 最终兜底：utf-8 忽略错误
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _pre_chunk_text(self, text: str) -> list[str]:
        """按配置的自然边界优先级预分块。

        策略：按边界优先级依次尝试，找到第一个能切分的边界就切；
        空字符串 "" 作为兜底表示按固定长度硬切。

        每个 pre-chunk 作为独立 Document 进入后续 splitter 流程，
        各自获得独立的 section_id，因此块间不需要 overlap。

        Args:
            text: 原始文本（已 strip）。

        Returns:
            预分块后的文本片段列表。
        """
        cfg = self._pre_chunk_config
        if not cfg.enabled or len(text) <= cfg.chunk_chars:
            return [text]

        chunk_size = cfg.chunk_chars
        boundaries = cfg.boundaries

        chunks = []
        pos = 0
        text_len = len(text)

        while pos < text_len:
            # 当前块的结束位置
            end = min(pos + chunk_size, text_len)

            # 未到文本末尾时，尝试在右半区找自然边界切分点
            if end < text_len:
                split_pos = self._find_split_pos(text, pos, end, boundaries)
                end = split_pos

            chunks.append(text[pos:end])

            # 已覆盖全文，结束
            if end >= text_len:
                break

            # 下个块从当前切分点开始（无 overlap，各自独立）
            pos = end

        # 过滤空块
        return [c for c in chunks if c.strip()]

    def _find_split_pos(
        self, text: str, start: int, end: int, boundaries: tuple[str, ...]
    ) -> int:
        """在 [start, end] 范围内找最佳切分点。

        搜索范围限定在后半区 [mid, end]，保证块大小不过小。
        按边界优先级依次尝试，返回找到的最右切分点 + 1（即下个块的起始）。
        """
        mid = start + (end - start) // 2

        for sep in boundaries:
            if sep == "":
                # 字符级兜底：在 end 处硬切
                return end

            # 在后半区从右往左找该分隔符
            search_region = text[mid:end]
            last_idx = search_region.rfind(sep)
            if last_idx != -1:
                # 返回分隔符之后的字符位置
                return mid + last_idx + len(sep)

        # 兜底：硬切
        return end

    def _process_single_file(self, file_path: str) -> list[Document]:
        """处理单个文本文件（含预分块）"""
        file_name = os.path.basename(file_path)

        try:
            file_sha256 = self._get_file_sha256(file_path)
            text = self._read_text(file_path)
            text_stripped = text.strip()

            if not text_stripped:
                self.logger.warning(f"[TextDataSource] 空文件: {file_name}")
                return []

            # 预分块
            sub_texts = self._pre_chunk_text(text_stripped)

            docs = []
            for idx, chunk_text in enumerate(sub_texts):
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
                        "pre_chunk_total": len(sub_texts),
                    },
                )
                docs.append(doc)

            # 更新统计（线程安全）
            with self._stats_lock:
                self._stats["success_files"] += 1

            self.logger.info(
                f"[TextDataSource] 读取成功 | file={file_name} | "
                f"chars={len(text_stripped)} | chunks={len(sub_texts)} | "
                f"sha256={file_sha256[:8]}..."
            )
            return docs

        except Exception as e:
            with self._stats_lock:
                self._stats["failed_files"] += 1

            self.logger.exception(
                f"[TextDataSource] 读取失败 | file={file_name} | error={e!s}",
            )
            return []

    def _collect_supported_files(self, root_dir: str) -> list[str]:
        """收集目录下所有支持的文件"""
        files = []
        for root, _, filenames in os.walk(root_dir):
            for fname in filenames:
                if Path(fname).suffix.lower() in self._supported_extensions:
                    files.append(os.path.abspath(os.path.join(root, fname)))
        return files

    def load_documents(self, reset_stats: bool = True) -> list[Document]:
        """加载目录下所有支持的文本文件（同步）"""
        self.logger.info(f"[TextDataSource] 开始加载目录: {self.folder_path}")

        text_files = self._collect_supported_files(self.folder_path)

        if not text_files:
            self.logger.warning(
                f"[TextDataSource] 目录中没有文本文件: {self.folder_path}"
            )
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats["total_files"] = len(text_files)
                self._stats["success_files"] = 0
                self._stats["failed_files"] = 0

        self.logger.info(
            f"[TextDataSource] 发现 {len(text_files)} 个文本文件，逐个同步处理"
        )

        all_docs = []
        for file_path in text_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[TextDataSource] 加载完成 | "
                f"总文件={self._stats['total_files']} | "
                f"成功={self._stats['success_files']} | "
                f"失败={self._stats['failed_files']} | "
                f"总Document={len(all_docs)}"
            )

        return all_docs

    def load_specific_files(
        self, file_paths: list[str], reset_stats: bool = True
    ) -> list[Document]:
        """加载指定的文本文件列表，用于增量上传（同步）"""
        self.logger.info(f"[TextDataSource] 增量加载指定文件 count={len(file_paths)}")
        text_files = []
        for fp in file_paths:
            p = Path(fp).resolve()
            if p.exists() and p.suffix.lower() in self._supported_extensions:
                text_files.append(str(p))
            else:
                self.logger.warning(f"[TextDataSource] 跳过非文本/不存在文件: {fp}")

        if not text_files:
            return []

        if reset_stats:
            with self._stats_lock:
                self._stats["total_files"] = len(text_files)
                self._stats["success_files"] = 0
                self._stats["failed_files"] = 0

        all_docs = []
        for file_path in text_files:
            docs = self._process_single_file(file_path)
            all_docs.extend(docs)

        with self._stats_lock:
            self.logger.info(
                f"[TextDataSource] 增量加载完成 | "
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
