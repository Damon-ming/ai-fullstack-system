# app-server/src/com/damon/ming/ai/rag/constructor/constructor.py
"""
章节重构服务 —— 纯合并分片，不含摘要逻辑。

线程编排由上层 RagChoreographer 负责。
线程池通过参数注入，本模块只做同步计算。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.rag.constructor.config import ConstructorConfig
from src.com.damon.ming.ai.rag.knowledge.metadata_keys import (
    FILE_ID,
    FILE_NAME,
    FILE_PATH,
    FILE_SHA256,
    HEADER_PATH,
    HEADING_PATH,
    RECONSTRUCTION_SKIP_CHARS,
    SECTION_ID,
    SECTION_SEQ,
    SOURCE_CONTEXT,
    SOURCE_METADATA_KEYS,
    SOURCE_REF_ID,
    TOTAL_PAGES,
)
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.app.thread_pools import run_in_pool
from src.com.damon.ming.log import pin

logger = pin("SectionReconstructor")

_SECTION_METADATA_KEYS = (
    FILE_ID,
    FILE_NAME,
    FILE_PATH,
    FILE_SHA256,
    SOURCE_REF_ID,
    SECTION_ID,
    HEADER_PATH,
    HEADING_PATH,
    *SOURCE_METADATA_KEYS,
    TOTAL_PAGES,
)


class SectionReconstructor:
    """章节重构服务，只做 chunk 合并，不做摘要。

    使用调用方注入的 retrieval 池，不管理线程池生命周期。
    """

    def __init__(
        self, retrieval_pool: ThreadPoolExecutor, config: dict[str, object]
    ) -> None:
        self._executor = retrieval_pool
        self._config = ConstructorConfig.from_mapping(config)

    async def reconstruct_sections_to_nodes(
        self,
        vector_store: BaseVectorStore,
        hit_nodes: list[TextNode],
    ) -> list[TextNode]:
        """
        从召回节点，拉取完整章节分片，每个 section_id 合并成单个 TextNode。

        将批量数据库查询提交到调用方提供的 retrieval 池。
        """
        if not hit_nodes:
            logger.warning("reconstruct_sections_to_nodes | hit_nodes 为空")
            return []

        section_keys = self._extract_section_keys(hit_nodes)
        if not section_keys:
            logger.warning("reconstruct_sections_to_nodes | 未提取到有效的章节键")
            return []

        all_section_nodes = await self._fetch_all_section_chunks(
            vector_store, section_keys, self._executor
        )
        group_map = self._group_chunks_by_section(all_section_nodes)
        return self._build_section_nodes(group_map, section_keys)

    def merge_nodes_to_text(
        self,
        nodes: list[TextNode],
        section_separator: str = "\n---\n",
    ) -> str:
        """将多个 TextNode 文本拼接为单个字符串。

        每个节点前按配置附加来源和标题层级，帮助模型理解内容归属。
        """
        if not nodes:
            return ""
        parts: list[str] = []
        for node in nodes:
            labels: list[str] = []
            source_context = node.metadata.get(SOURCE_CONTEXT)
            if source_context:
                labels.append(
                    self._config.source_label_template.replace(
                        "{value}", str(source_context)
                    )
                )
            heading = node.metadata.get(HEADING_PATH, "")
            if heading:
                # heading_path 格式为 "/父标题/子标题/"
                clean_path = heading.strip("/").replace(
                    "/", self._config.heading_separator
                )
                if clean_path:
                    labels.append(
                        self._config.heading_label_template.replace(
                            "{value}", clean_path
                        )
                    )
            prefix = "\n".join(labels) + "\n" if labels else ""
            parts.append(f"{prefix}{node.text}")
        return section_separator.join(parts)

    # ── 私有：合并逻辑 ────────────────────────────────────────────────

    def _extract_section_keys(self, nodes: list[TextNode]) -> set[tuple[str, str]]:
        """从节点列表中提取唯一的 (file_sha256, section_id) 键"""
        section_keys = set()
        for node in nodes:
            file_sha256 = node.metadata.get(FILE_SHA256)
            section_id = node.metadata.get(SECTION_ID)
            if file_sha256 and section_id:
                section_keys.add((file_sha256, section_id))
        return section_keys

    async def _fetch_all_section_chunks(
        self,
        vector_store: BaseVectorStore,
        section_keys: set[tuple[str, str]],
        executor: ThreadPoolExecutor,
    ) -> list[TextNode]:
        """批量获取所有章节的完整分片。

        通过 vector_store.get_by_metadata_batch 合并为单次 OR 查询，
        将 N 次数据库扫描降为 1 次，显著减少向量查询耗时。
        executor 由上层 RagChoreographer 注入，通过统一线程池入口提交任务。
        """
        if not section_keys:
            return []

        filters = [
            {FILE_SHA256: file_sha256, SECTION_ID: section_id}
            for file_sha256, section_id in section_keys
        ]

        try:
            all_nodes = await run_in_pool(
                executor,
                vector_store.get_by_metadata_batch,
                filters,
            )
        except Exception as e:
            logger.warning(f"章节分片批量查询失败: {e}")
            return []
        return all_nodes

    def _group_chunks_by_section(
        self, chunks: list[TextNode]
    ) -> dict[tuple[str, str], list[TextNode]]:
        """按 (file_sha256, section_id) 分组所有 chunk 分片"""
        group_map: dict[tuple[str, str], list[TextNode]] = {}
        for chunk in chunks:
            file_sha256 = chunk.metadata.get(FILE_SHA256)
            section_id = chunk.metadata.get(SECTION_ID)
            if file_sha256 is None or section_id is None:
                continue
            key = (file_sha256, section_id)
            if key not in group_map:
                group_map[key] = []
            group_map[key].append(chunk)
        return group_map

    def _build_section_nodes(
        self,
        group_map: dict[tuple[str, str], list[TextNode]],
        target_keys: set[tuple[str, str]],
    ) -> list[TextNode]:
        """将同 section_id 下的多个 chunk 合并为单个 TextNode"""
        result_nodes = []
        for key in target_keys:
            section_nodes = group_map.get(key, [])
            if not section_nodes:
                continue
            full_section = self._merge_chunks(section_nodes)
            if not full_section:
                continue

            first_node = section_nodes[0]
            metadata = {
                field: first_node.metadata[field]
                for field in _SECTION_METADATA_KEYS
                if field in first_node.metadata
            }
            merged_node = TextNode(
                text=full_section,
                metadata=metadata,
            )
            result_nodes.append(merged_node)
        return result_nodes

    def _merge_chunks(self, section_chunks: list[TextNode]) -> str | None:
        """按 section_seq 排序，去掉各块标记的重复前缀后拼接。"""
        if not section_chunks:
            return None
        section_chunks.sort(key=lambda x: x.metadata.get(SECTION_SEQ, 0))
        parts = []
        for node in section_chunks:
            skip_chars = node.metadata.get(RECONSTRUCTION_SKIP_CHARS, 0)
            if type(skip_chars) is not int or not 0 <= skip_chars <= len(node.text):
                logger.warning("章节分片的 reconstruction_skip_chars 无效，保留原文")
                skip_chars = 0
            content = node.text[skip_chars:]
            if content:
                parts.append(content)
        return "\n".join(parts)
