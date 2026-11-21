# app-server/src/com/damon/ming/ai/rag/spliter/spliter.py
"""
文档分块器 —— 纯同步实现，线程编排由上层 RagChoreographer 负责。

本模块只负责"给定 Document 列表，返回切分后的 TextNode 列表"，
不感知线程池、取消令牌等基础设施。
"""

import hashlib
import re
import threading
from abc import ABC, abstractmethod
from collections import defaultdict

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser, TokenTextSplitter
from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.rag.knowledge.metadata_keys import (
    CHAR_END,
    CHAR_START,
    CHUNK_ID,
    CHUNK_LENGTH,
    CONTENT_TYPE,
    FILE_NAME,
    FILE_PATH,
    FILE_SHA256,
    HEADER_PATH,
    HEADING_PATH,
    PAGE,
    PAGE_END,
    PAGE_INDEX,
    PAGE_START,
    RECONSTRUCTION_SKIP_CHARS,
    SECTION_GROUP,
    SECTION_ID,
    SECTION_SEQ,
    SOURCE_METADATA_KEYS,
    TOKEN_COUNT,
    TOTAL_CHUNKS_IN_SECTION,
    TOTAL_PAGES,
)
from src.com.damon.ming.log import pin

from ..tokenizer.base_tokenizer import BaseTokenizer
from .table_splitter import TableAwareSplitter

_MARKDOWN_HEADING_RE = re.compile(r"(?m)^ {0,3}#{1,6}[ \t]+\S")
# 显式分组及无标题页面按较小单元重建；自然标题章节保留更多上下文。
_MAX_GROUPED_CHUNKS_PER_SECTION = 2
_MAX_HEADED_CHUNKS_PER_SECTION = 5


class BaseDocumentSplitter(ABC):
    """文档分割器抽象接口"""

    @abstractmethod
    def split(
        self, docs: list[Document], max_chunk_size: int | None = None
    ) -> list[TextNode]:
        pass


class StructuredDocumentSplitter(BaseDocumentSplitter):
    """统一文档分块器，按 Markdown 标题及表格边界处理解析后的文本。

    上层 RagChoreographer 使用 asyncio.to_thread 将本类的调用提交到线程池。
    """

    # 类级别锁，用于统计同步
    _stats_lock = threading.Lock()

    def __init__(
        self,
        tokenizer: BaseTokenizer,
        max_chunk_token_size: int,
        chunk_overlap: int | None = None,
    ):
        if type(max_chunk_token_size) is not int or max_chunk_token_size <= 0:
            raise ValueError("max_chunk_token_size 必须是正整数")
        if chunk_overlap is None:
            chunk_overlap = 0
        if (
            type(chunk_overlap) is not int
            or not 0 <= chunk_overlap < max_chunk_token_size
        ):
            raise ValueError("chunk_overlap 必须是小于 max_chunk_token_size 的非负整数")
        self.max_chunk_token_size = max_chunk_token_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tokenizer
        self.logger = pin("StructuredDocumentSplitter")
        self.md_parser = MarkdownNodeParser()
        self._table_splitter = TableAwareSplitter(self._count_tokens)

        # 统计信息（线程安全）
        self.stats = {
            "total_chunks": 0,
            "total_sections": 0,
            "split_sections": 0,
            "errors": 0,
        }

    def _gen_section_id(
        self, file_sha256: str, node_text: str, section_group: str | None = None
    ):
        identity = (
            f"{section_group}:{node_text}" if section_group is not None else node_text
        )
        seg_hash = hashlib.md5(identity.encode(), usedforsecurity=False).hexdigest()[
            :16
        ]
        return f"section_{file_sha256}_{seg_hash}"

    def _count_tokens(self, text: str) -> int:
        try:
            return self.tokenizer.count_tokens(text)
        except Exception:
            # tokenizer 异常时保守估算：中文场景 1 字符 ≈ 1-3 token，
            # 取 len//2 确保不会因为低估而漏掉需要分割的超大章节
            return max(len(text) // 2, 1)

    def _merge_documents_by_file(
        self, docs: list[Document]
    ) -> tuple[list[Document], dict[tuple[str, str | None], list]]:
        """按文件及显式分组合并页面；无标题文本按页形成独立章节。"""
        file_groups = defaultdict(list)
        for d in docs:
            file_sha256 = d.metadata.get(FILE_SHA256)
            if file_sha256:
                file_groups[file_sha256].append(d)

        merged_docs = []
        file_page_mapping = {}
        sep = "\n\n"
        sep_len = len(sep)

        for file_sha256, page_doc_list in file_groups.items():
            page_doc_list.sort(key=lambda x: x.metadata[PAGE_INDEX])
            has_headings = any(
                _MARKDOWN_HEADING_RE.search(page_doc.text) for page_doc in page_doc_list
            )
            logical_groups = defaultdict(list)
            for page_doc in page_doc_list:
                group = page_doc.metadata.get(SECTION_GROUP)
                if group is None and not has_headings:
                    group = f"page:{page_doc.metadata[PAGE_INDEX]}"
                logical_groups[group].append(page_doc)

            for group, group_docs in logical_groups.items():
                sample_meta = group_docs[0].metadata
                text_parts = []
                offset_records = []
                current_global_pos = 0

                for page_doc in group_docs:
                    page_text = page_doc.text
                    page_no = page_doc.metadata[PAGE]
                    text_len = len(page_text)
                    offset_records.append(
                        (current_global_pos, current_global_pos + text_len, page_no)
                    )
                    text_parts.append(page_text)
                    current_global_pos += text_len
                    text_parts.append(sep)
                    current_global_pos += sep_len

                metadata = {
                    FILE_NAME: sample_meta[FILE_NAME],
                    FILE_SHA256: file_sha256,
                    FILE_PATH: sample_meta[FILE_PATH],
                    TOTAL_PAGES: sample_meta[TOTAL_PAGES],
                }
                if group is not None:
                    metadata[SECTION_GROUP] = group
                metadata.update(
                    {
                        key: sample_meta[key]
                        for key in SOURCE_METADATA_KEYS
                        if key in sample_meta
                    }
                )
                merged_docs.append(
                    Document(text="".join(text_parts).strip(), metadata=metadata)
                )
                file_page_mapping[(file_sha256, group)] = offset_records

        return merged_docs, file_page_mapping

    def _lookup_page(self, global_offset: int, offset_list):
        """根据全局偏移查找页码"""
        for g_start, g_end, p_no in offset_list:
            if g_start <= global_offset < g_end:
                return p_no
        return None

    def _process_single_document(
        self,
        doc: Document,
        page_offset_list: list,
        max_chunk_size: int,
        chunk_overlap: int,
        token_splitter: TokenTextSplitter,
    ) -> list[TextNode]:
        """处理单个文档（同步）"""
        limit = max_chunk_size
        doc_nodes = []
        doc_text = doc.text.strip()

        if not doc_text:
            return doc_nodes

        file_sha256 = doc.metadata.get(FILE_SHA256, "unknown")
        file_name = doc.metadata.get(FILE_NAME, "unknown")
        section_group = doc.metadata.get(SECTION_GROUP)
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

            section_id = self._gen_section_id(
                file_sha256, section_raw_text, section_group
            )
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

                # 表格感知分割：检测表格边界，确保表格不被切碎
                table_blocks = self._table_splitter.find_table_blocks(section_raw_text)
                if table_blocks:
                    sub_nodes = self._table_splitter.split(
                        section_raw_text, table_blocks, limit, token_splitter
                    )
                else:
                    sub_nodes = token_splitter.get_nodes_from_documents(
                        [Document(text=section_raw_text)]
                    )

                section_chunk_limit = (
                    _MAX_GROUPED_CHUNKS_PER_SECTION
                    if section_group is not None
                    else _MAX_HEADED_CHUNKS_PER_SECTION
                )
                bounded = len(sub_nodes) > section_chunk_limit
                if bounded:
                    with self._stats_lock:
                        self.stats["total_sections"] += (
                            len(sub_nodes) - 1
                        ) // section_chunk_limit

                previous_node: TextNode | None = None
                for seq, sub_node in enumerate(sub_nodes):
                    if not sub_node.text.strip():
                        continue

                    if HEADER_PATH in section_node.metadata:
                        sub_node.metadata.setdefault(
                            HEADER_PATH, section_node.metadata[HEADER_PATH]
                        )

                    group_index = seq // section_chunk_limit if bounded else 0
                    chunk_section_id = (
                        f"{section_id}_{group_index}" if bounded else section_id
                    )
                    chunk_section_seq = seq % section_chunk_limit if bounded else seq
                    chunks_in_group = (
                        min(
                            section_chunk_limit,
                            len(sub_nodes) - group_index * section_chunk_limit,
                        )
                        if bounded
                        else len(sub_nodes)
                    )

                    if (
                        previous_node is not None
                        and chunk_section_seq > 0
                        and RECONSTRUCTION_SKIP_CHARS not in sub_node.metadata
                        and previous_node.metadata.get(CONTENT_TYPE) != "table"
                        and sub_node.metadata.get(CONTENT_TYPE) != "table"
                    ):
                        sub_node.metadata[RECONSTRUCTION_SKIP_CHARS] = (
                            self._overlap_prefix_chars(
                                previous_node.text, sub_node.text, chunk_overlap
                            )
                        )
                    if bounded and chunk_section_seq == 0:
                        sub_node.metadata[RECONSTRUCTION_SKIP_CHARS] = 0

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
                        file_sha256=file_sha256,
                        file_name=file_name,
                        section_id=chunk_section_id,
                        section_seq=chunk_section_seq,
                        char_start=real_start,
                        char_end=real_end,
                        total_chunks_in_section=chunks_in_group,
                    )

                    # 回填页码
                    p_start = self._lookup_page(real_start, page_offset_list)
                    p_end = self._lookup_page(
                        max(real_end - 1, real_start), page_offset_list
                    )
                    if p_start is not None:
                        sub_node.metadata[PAGE_START] = p_start
                    if p_end is not None:
                        sub_node.metadata[PAGE_END] = p_end

                    doc_nodes.append(sub_node)
                    previous_node = sub_node
            else:
                # 不分割
                self._attach_metadata(
                    node=section_node,
                    file_sha256=file_sha256,
                    file_name=file_name,
                    section_id=section_id,
                    section_seq=0,
                    char_start=section_start,
                    char_end=section_end,
                    total_chunks_in_section=1,
                )

                p_start = self._lookup_page(section_start, page_offset_list)
                p_end = self._lookup_page(
                    max(section_end - 1, section_start), page_offset_list
                )
                if p_start is not None:
                    section_node.metadata[PAGE_START] = p_start
                if p_end is not None:
                    section_node.metadata[PAGE_END] = p_end

                doc_nodes.append(section_node)

        source_details = {
            key: doc.metadata[key]
            for key in SOURCE_METADATA_KEYS
            if key in doc.metadata
        }
        for node in doc_nodes:
            node.metadata.update(source_details)
        return doc_nodes

    def split(
        self,
        docs: list[Document],
        max_chunk_size: int | None = None,
        reset_stats: bool = True,
        chunk_overlap: int | None = None,
    ) -> list[TextNode]:
        """分割文档列表（同步）。

        注意：本方法本身是同步的。当需要并行处理多个文档时，
        上层 RagChoreographer 应将每个文档的分割作为独立任务提交到线程池，
        而非在本方法内部做并行。这样可以保证：
        - RagChoreographer 控制线程生命周期
        - 取消时 RagChoreographer 只需取消未开始的 future

        Args:
            docs: 待分割的 Document 列表。
            max_chunk_size: 最大 chunk token 大小，None 时使用构造时默认值。
            reset_stats: True 时重置统计后开始（默认），False 时累加到已有统计。
            chunk_overlap: 本次切分的重叠 token 数，None 时使用配置值，0 时禁用。
        """
        if not docs:
            return []

        effective_size = (
            self.max_chunk_token_size if max_chunk_size is None else max_chunk_size
        )
        effective_overlap = (
            self.chunk_overlap if chunk_overlap is None else chunk_overlap
        )
        if type(effective_size) is not int or effective_size <= 0:
            raise ValueError("max_chunk_size 必须是正整数")
        if (
            type(effective_overlap) is not int
            or not 0 <= effective_overlap < effective_size
        ):
            raise ValueError("chunk_overlap 必须是小于 max_chunk_size 的非负整数")
        token_splitter = TokenTextSplitter(
            chunk_size=effective_size, chunk_overlap=effective_overlap
        )

        self.logger.info(f"[Splitter] 开始分割 {len(docs)} 个Document")

        # 统计重置（默认行为）或累加（reset_stats=False）
        if reset_stats:
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
        #    并行由 RagChoreographer 在更高层编排（按文件粒度提交到线程池）
        all_nodes = []

        for doc in merged_docs:
            try:
                nodes = self._process_single_document(
                    doc,
                    file_page_mapping[
                        (doc.metadata[FILE_SHA256], doc.metadata.get(SECTION_GROUP))
                    ],
                    effective_size,
                    effective_overlap,
                    token_splitter,
                )
                all_nodes.extend(nodes)
            except Exception:
                self.logger.exception(
                    f"[Splitter] 处理文档失败 | "
                    f"file={doc.metadata.get(FILE_NAME, 'unknown')}",
                )
                with self._stats_lock:
                    self.stats["errors"] += 1
                raise

        # 更新统计
        with self._stats_lock:
            self.stats["total_chunks"] = len(all_nodes)

        self.logger.info(
            f"[Splitter] 分割完成 | "
            f"总chunk={len(all_nodes)} | "
            f"章节数={self.stats['total_sections']} | "
            f"触发分割={self.stats['split_sections']}"
        )

        return all_nodes

    def _overlap_prefix_chars(
        self, previous: str, current: str, chunk_overlap: int
    ) -> int:
        """返回当前块开头与前一块结尾重复的字符数。"""
        if chunk_overlap <= 0 or not previous or not current:
            return 0

        # KMP 查找最长的「前块后缀 == 当前块前缀」，避免逐长度比较。
        prefix = [0] * len(current)
        matched = 0
        for i in range(1, len(current)):
            while matched and current[i] != current[matched]:
                matched = prefix[matched - 1]
            if current[i] == current[matched]:
                matched += 1
            prefix[i] = matched

        matched = 0
        for char in previous:
            while matched and (matched == len(current) or char != current[matched]):
                matched = prefix[matched - 1]
            if char == current[matched]:
                matched += 1

        # 避免将正文中正常重复、却超过配置 overlap 的内容误判为切分重叠。
        while matched and self._count_tokens(current[:matched]) > chunk_overlap:
            matched = prefix[matched - 1]
        return matched

    def _attach_metadata(
        self,
        node: TextNode,
        file_sha256: str,
        file_name: str,
        section_id: str,
        section_seq: int,
        char_start: int,
        char_end: int,
        total_chunks_in_section: int,
    ):
        """附加元数据到节点"""
        chunk_hash = hashlib.md5(
            f"{section_id}:{section_seq}:{node.text}".encode(),
            usedforsecurity=False,
        ).hexdigest()[:16]
        chunk_id = f"chunk_{file_sha256}_{chunk_hash}"

        node.node_id = chunk_id
        node.metadata[CHUNK_ID] = chunk_id
        node.metadata[FILE_NAME] = file_name
        node.metadata[FILE_SHA256] = file_sha256
        node.metadata[SECTION_ID] = section_id
        node.metadata[SECTION_SEQ] = section_seq
        node.metadata.setdefault(RECONSTRUCTION_SKIP_CHARS, 0)
        node.metadata[TOTAL_CHUNKS_IN_SECTION] = total_chunks_in_section
        node.metadata[CHAR_START] = char_start
        node.metadata[CHAR_END] = char_end
        node.metadata[CHUNK_LENGTH] = len(node.text)
        node.metadata[TOKEN_COUNT] = self._count_tokens(node.text)
        # 保留 MarkdownNodeParser 自动生成的章节标题链，供 LLM 理解上下文层级
        if HEADER_PATH in node.metadata:
            node.metadata[HEADING_PATH] = node.metadata[HEADER_PATH]

    def get_stats(self) -> dict:
        """获取分割统计信息"""
        with self._stats_lock:
            return self.stats.copy()
