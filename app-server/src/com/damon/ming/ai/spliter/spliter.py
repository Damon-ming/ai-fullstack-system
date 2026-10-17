# app-server/src/com/damon/ming/ai/spliter/spliter.py
"""
文档分块器 —— 纯同步实现，线程编排由上层 RAGContainer 负责。

本模块只负责"给定 Document 列表，返回切分后的 TextNode 列表"，
不感知线程池、取消令牌等基础设施。
"""

import hashlib
import threading
from abc import ABC, abstractmethod
from collections import defaultdict

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser, TokenTextSplitter
from llama_index.core.schema import TextNode
from src.com.damon.ming.log import pin

from ..tokenizer.base_tokenizer import BaseTokenizer


class BaseDocumentSplitter(ABC):
    """文档分割器抽象接口"""

    @abstractmethod
    def split(
        self, docs: list[Document], max_chunk_size: int | None = None
    ) -> list[TextNode]:
        pass


class MarkdownDocumentSplitter(BaseDocumentSplitter):
    """Markdown 文档分块器，同步处理。

    上层 RAGContainer 使用 asyncio.to_thread 将本类的调用提交到线程池。
    """

    # 类级别锁，用于统计同步
    _stats_lock = threading.Lock()

    def __init__(
        self,
        tokenizer: BaseTokenizer,
        max_chunk_token_size: int = 1024,
        chunk_overlap: int = 120,
    ):
        self.max_chunk_token_size = max_chunk_token_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tokenizer
        self.logger = pin("MarkdownDocumentSplitter")
        self.md_parser = MarkdownNodeParser()
        self.token_splitter = TokenTextSplitter(
            chunk_size=max_chunk_token_size, chunk_overlap=chunk_overlap
        )

        # 统计信息（线程安全）
        self.stats = {
            "total_chunks": 0,
            "total_sections": 0,
            "split_sections": 0,
            "errors": 0,
        }

    def _gen_section_id(self, file_md5: str, node_text: str):
        seg_hash = hashlib.md5(node_text.encode("utf-8")).hexdigest()[:16]
        return f"section_{file_md5}_{seg_hash}"

    def _count_tokens(self, text: str) -> int:
        try:
            return self.tokenizer.count_tokens(text)
        except Exception:
            return len(text)

    def _merge_documents_by_file(
        self, docs: list[Document]
    ) -> tuple[list[Document], dict]:
        """合并同一文件的页面为一个Document"""
        file_groups = defaultdict(list)
        for d in docs:
            fm5 = d.metadata.get("file_md5")
            if fm5:
                file_groups[fm5].append(d)

        merged_docs = []
        file_page_mapping = {}
        sep = "\n\n"
        sep_len = len(sep)

        for file_md5, page_doc_list in file_groups.items():
            # 页面按页码排序
            page_doc_list.sort(key=lambda x: x.metadata["page_index"])
            sample_meta = page_doc_list[0].metadata

            text_parts = []
            offset_records = []
            current_global_pos = 0

            for page_doc in page_doc_list:
                page_text = page_doc.text
                page_no = page_doc.metadata["page"]
                text_len = len(page_text)

                offset_records.append(
                    (current_global_pos, current_global_pos + text_len, page_no)
                )
                text_parts.append(page_text)
                current_global_pos += text_len
                text_parts.append(sep)
                current_global_pos += sep_len

            merged_full_text = "".join(text_parts)
            merged_doc = Document(
                text=merged_full_text.strip(),
                metadata={
                    "file_name": sample_meta["file_name"],
                    "file_md5": file_md5,
                    "file_path": sample_meta["file_path"],
                    "total_pages": sample_meta["total_pages"],
                },
            )
            merged_docs.append(merged_doc)
            file_page_mapping[file_md5] = offset_records

        return merged_docs, file_page_mapping

    def _lookup_page(self, global_offset: int, offset_list):
        """根据全局偏移查找页码"""
        for g_start, g_end, p_no in offset_list:
            if g_start <= global_offset < g_end:
                return p_no
        return None

    def _process_single_document(
        self, doc: Document, page_offset_list: list, max_chunk_size: int | None = None
    ) -> list[TextNode]:
        """处理单个文档（同步）"""
        limit = max_chunk_size or self.max_chunk_token_size
        doc_nodes = []
        doc_text = doc.text.strip()

        if not doc_text:
            return doc_nodes

        file_md5 = doc.metadata.get("file_md5", "unknown")
        file_name = doc.metadata.get("file_name", "unknown")
        doc_total_len = len(doc_text)

        # Markdown按标题切章节
        md_section_nodes = self.md_parser.get_nodes_from_documents([doc])
        if not md_section_nodes:
            md_section_nodes = [TextNode(text=doc_text)]

        self.logger.debug(
            f"[Splitter] 处理文档: {file_name} | "
            f"章节数: {len(md_section_nodes)} | "
            f"文档长度: {doc_total_len} 字符"
        )

        # 处理每个章节
        for section_node in md_section_nodes:
            section_raw_text = section_node.text.strip()
            if not section_raw_text:
                continue

            # 更新统计（线程安全）
            with self._stats_lock:
                self.stats["total_sections"] += 1

            section_id = self._gen_section_id(file_md5, section_raw_text)
            section_start = section_node.start_char_idx or 0
            section_end = section_node.end_char_idx or len(section_raw_text)
            section_tokens = self._count_tokens(section_raw_text)

            if section_tokens > limit:
                # 触发分割
                with self._stats_lock:
                    self.stats["split_sections"] += 1

                self.logger.debug(
                    f"[Splitter] 超大章节触发分割 | file={file_name} | "
                    f"tokens={section_tokens} | limit={limit}"
                )

                sub_nodes = self.token_splitter.get_nodes_from_documents(
                    [Document(text=section_raw_text)]
                )

                for seq, sub_node in enumerate(sub_nodes):
                    if not sub_node.text.strip():
                        continue

                    real_start = section_start + (sub_node.start_char_idx or 0)
                    real_end = section_start + (
                        sub_node.end_char_idx or len(sub_node.text)
                    )
                    real_start = max(0, min(real_start, doc_total_len - 1))
                    real_end = max(0, min(real_end, doc_total_len))

                    if real_start > real_end:
                        real_start, real_end = real_end, real_start

                    self._attach_metadata(
                        node=sub_node,
                        file_md5=file_md5,
                        file_name=file_name,
                        section_id=section_id,
                        section_seq=seq,
                        char_start=real_start,
                        char_end=real_end,
                        total_chunks_in_section=len(sub_nodes),
                    )

                    # 回填页码
                    p_start = self._lookup_page(real_start, page_offset_list)
                    p_end = self._lookup_page(real_end, page_offset_list)
                    if p_start is not None:
                        sub_node.metadata["page_start"] = p_start
                    if p_end is not None:
                        sub_node.metadata["page_end"] = p_end

                    doc_nodes.append(sub_node)
            else:
                # 不分割
                self._attach_metadata(
                    node=section_node,
                    file_md5=file_md5,
                    file_name=file_name,
                    section_id=section_id,
                    section_seq=0,
                    char_start=section_start,
                    char_end=section_end,
                    total_chunks_in_section=1,
                )

                p_start = self._lookup_page(section_start, page_offset_list)
                p_end = self._lookup_page(section_end, page_offset_list)
                if p_start is not None:
                    section_node.metadata["page_start"] = p_start
                if p_end is not None:
                    section_node.metadata["page_end"] = p_end

                doc_nodes.append(section_node)

        return doc_nodes

    def split(
        self,
        docs: list[Document],
        max_chunk_size: int | None = None,
    ) -> list[TextNode]:
        """分割文档列表（同步）。

        注意：本方法本身是同步的。当需要并行处理多个文档时，
        上层 RAGContainer 应将每个文档的分割作为独立任务提交到线程池，
        而非在本方法内部做并行。这样可以保证：
        - RAGContainer 控制线程生命周期
        - 取消时 RAGContainer 只需取消未开始的 future
        """
        if not docs:
            return []

        self.logger.info(f"[Splitter] 开始分割 {len(docs)} 个Document")

        # 重置统计
        with self._stats_lock:
            self.stats = {
                "total_chunks": 0,
                "total_sections": 0,
                "split_sections": 0,
                "errors": 0,
            }

        # 1. 按文件合并页面
        merged_docs, file_page_mapping = self._merge_documents_by_file(docs)
        self.logger.info(f"[Splitter] 合并为 {len(merged_docs)} 个文档")

        # 2. 逐个同步处理每个文档（无内部并行）
        #    并行由 RAGContainer 在更高层编排（按文件粒度提交到线程池）
        all_nodes = []
        errors = 0

        for doc in merged_docs:
            try:
                nodes = self._process_single_document(
                    doc,
                    file_page_mapping[doc.metadata["file_md5"]],
                    max_chunk_size,
                )
                all_nodes.extend(nodes)
            except Exception as e:
                errors += 1
                self.logger.error(
                    f"[Splitter] 处理文档失败 | "
                    f"file={doc.metadata.get('file_name', 'unknown')} | "
                    f"error={e}",
                    exc_info=True,
                )
                with self._stats_lock:
                    self.stats["errors"] += 1

        # 更新统计
        with self._stats_lock:
            self.stats["total_chunks"] = len(all_nodes)

        self.logger.info(
            f"[Splitter] 分割完成 | "
            f"总chunk={len(all_nodes)} | "
            f"章节数={self.stats['total_sections']} | "
            f"触发分割={self.stats['split_sections']} | "
            f"错误={errors}"
        )

        return all_nodes

    def _attach_metadata(
        self,
        node: TextNode,
        file_md5: str,
        file_name: str,
        section_id: str,
        section_seq: int,
        char_start: int,
        char_end: int,
        total_chunks_in_section: int,
    ):
        """附加元数据到节点"""
        text_hash = hashlib.md5(node.text.encode("utf-8")).hexdigest()[:16]
        chunk_id = f"chunk_{file_md5}_{text_hash}"

        node.node_id = chunk_id
        node.metadata["chunk_id"] = chunk_id
        node.metadata["file_name"] = file_name
        node.metadata["file_md5"] = file_md5
        node.metadata["section_id"] = section_id
        node.metadata["section_seq"] = section_seq
        node.metadata["total_chunks_in_section"] = total_chunks_in_section
        node.metadata["char_start"] = char_start
        node.metadata["char_end"] = char_end
        node.metadata["chunk_length"] = len(node.text)
        node.metadata["token_count"] = self._count_tokens(node.text)

    def get_stats(self) -> dict:
        """获取分割统计信息"""
        with self._stats_lock:
            return self.stats.copy()

    def verify_chunk_position(
        self, chunk: TextNode, original_document: Document
    ) -> bool:
        """验证chunk位置信息"""
        try:
            start = chunk.metadata.get("char_start", -1)
            end = chunk.metadata.get("char_end", -1)

            if start < 0 or end < 0 or start >= end:
                self.logger.warning(f"无效的位置信息: start={start}, end={end}")
                return False

            extracted = original_document.text[start:end]
            if extracted.strip() != chunk.text.strip():
                self.logger.warning(
                    f"位置验证失败！原始切片前100字符: {extracted[:100]}... | "
                    f"Chunk前100字符: {chunk.text[:100]}..."
                )
                return False
            return True

        except Exception as e:
            self.logger.error(f"验证位置时出错: {e}")
            return False

    def reconstruct_section(
        self, chunks: list[TextNode], section_id: str
    ) -> str | None:
        """重建章节"""
        section_chunks = [
            c for c in chunks if c.metadata.get("section_id") == section_id
        ]

        if not section_chunks:
            return None

        section_chunks.sort(key=lambda x: x.metadata.get("section_seq", 0))
        return "\n".join([c.text for c in section_chunks])
