# app-server/src/com/damon/ming/ai/constructor/constructor.py
"""
章节重构服务 —— 纯合并分片，不含摘要逻辑。

线程编排由上层 RAGContainer 负责。
线程池通过参数注入，本模块只做同步计算。
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.log import pin

logger = pin("SectionReconstructor")


class SectionReconstructor:
    """章节重构服务，只做 chunk 合并，不做摘要。

    不持有线程池——上层 RAGContainer 通过参数注入 executor。
    """

    async def reconstruct_sections_to_nodes(
        self,
        vector_store: BaseVectorStore,
        hit_nodes: list[TextNode],
        executor: ThreadPoolExecutor,
    ) -> list[TextNode]:
        """
        从召回节点，拉取完整章节分片，每个 section_id 合并成单个 TextNode。

        内部并发获取多个章节的分片，每个分片查询通过注入的 executor 提交。
        executor 由上层 RAGContainer 注入，不持有线程池。
        """
        if not hit_nodes:
            logger.warning("reconstruct_sections_to_nodes | hit_nodes 为空")
            return []

        section_keys = self._extract_section_keys(hit_nodes)
        if not section_keys:
            logger.warning("reconstruct_sections_to_nodes | 未提取到有效的章节键")
            return []

        all_section_nodes = await self._fetch_all_section_chunks(
            vector_store, section_keys, executor
        )
        group_map = self._group_chunks_by_section(all_section_nodes)
        return self._build_section_nodes(group_map, section_keys)

    def merge_nodes_to_text(
        self,
        nodes: list[TextNode],
        section_separator: str = "\n---\n",
    ) -> str:
        """将多个 TextNode 文本拼接为单个字符串。"""
        if not nodes:
            return ""
        return section_separator.join(n.text for n in nodes)

    # ── 私有：合并逻辑 ────────────────────────────────────────────────

    def _extract_section_keys(self, nodes: list[TextNode]) -> set[tuple[str, str]]:
        """从节点列表中提取唯一的 (file_md5, section_id) 键"""
        section_keys = set()
        for node in nodes:
            file_md5 = node.metadata.get("file_md5")
            section_id = node.metadata.get("section_id")
            if file_md5 and section_id:
                section_keys.add((file_md5, section_id))
        return section_keys

    async def _fetch_all_section_chunks(
        self,
        vector_store: BaseVectorStore,
        section_keys: set[tuple[str, str]],
        executor: ThreadPoolExecutor,
    ) -> list[TextNode]:
        """批量获取所有章节的完整分片（并发执行）。

        executor 由上层 RAGContainer 注入，通过 run_in_executor 提交到集中式线程池。
        """
        if not section_keys:
            return []

        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                executor,
                vector_store.get_by_metadata,
                {"file_md5": file_md5, "section_id": section_id},
            )
            for file_md5, section_id in section_keys
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_nodes: list[TextNode] = []
        for nodes in results:
            if isinstance(nodes, Exception):
                logger.warning(f"章节分片查询失败: {nodes}")
                continue
            all_nodes.extend(nodes)
        return all_nodes

    def _group_chunks_by_section(
        self, chunks: list[TextNode]
    ) -> dict[tuple[str, str], list[TextNode]]:
        """按 (file_md5, section_id) 分组所有 chunk 分片"""
        group_map: dict[tuple[str, str], list[TextNode]] = {}
        for chunk in chunks:
            file_md5 = chunk.metadata.get("file_md5")
            section_id = chunk.metadata.get("section_id")
            if file_md5 is None or section_id is None:
                continue
            key = (file_md5, section_id)
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
            merged_node = TextNode(
                text=full_section,
                metadata=first_node.metadata.copy(),
            )
            result_nodes.append(merged_node)
        return result_nodes

    def _merge_chunks(self, section_chunks: list[TextNode]) -> str | None:
        """按 section_seq 排序并拼接同章节的 chunk 文本"""
        if not section_chunks:
            return None
        section_chunks.sort(key=lambda x: x.metadata.get("section_seq", 0))
        return "\n".join([node.text for node in section_chunks])
