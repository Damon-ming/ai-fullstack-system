# app-server/src/com/damon/ming/ai/constructor/constructor.py

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.summary import BaseSummarizer
from src.com.damon.ming.ai.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.log import pin

logger = pin("SectionReconstructor")


class SectionReconstructor:
    def __init__(
        self, tokenizer: BaseTokenizer, summarizer: BaseSummarizer | None = None
    ):
        self.tokenizer = tokenizer
        self.summarizer = summarizer
        # 单个章节的摘要触发阈值（token数）
        self.section_summary_threshold = 1000
        # 摘要生成的目标长度
        self.summary_max_tokens = 1200

    def debug_memory_reconstruct(
        self, chunks: list[TextNode], section_id: str
    ) -> str | None:
        section_chunks = [
            c for c in chunks if c.metadata.get("section_id") == section_id
        ]
        return self._merge_chunks(section_chunks)

    async def retrieve_and_reconstruct(
        self, vector_store, hit_node: TextNode
    ) -> str | None:
        file_md5 = hit_node.metadata.get("file_md5")
        section_id = hit_node.metadata.get("section_id")
        if not file_md5 or not section_id:
            return None

        filter_condition = {"file_md5": file_md5, "section_id": section_id}

        section_nodes: list[TextNode] = await vector_store.asearch(
            metadata_filter=filter_condition
        )
        return self._merge_chunks(section_nodes)

    def retrieve_and_reconstruct_sync(
        self, vector_store, hit_node: TextNode
    ) -> str | None:
        file_md5 = hit_node.metadata.get("file_md5")
        section_id = hit_node.metadata.get("section_id")
        if not file_md5 or not section_id:
            return None

        filter_condition = {"file_md5": file_md5, "section_id": section_id}
        section_nodes: list[TextNode] = vector_store.query(
            metadata_filter=filter_condition
        )
        return self._merge_chunks(section_nodes)

    def _merge_chunks(self, section_chunks: list[TextNode]) -> str | None:
        if not section_chunks:
            return None

        section_chunks.sort(key=lambda x: x.metadata.get("section_seq", 0))
        return "\n".join([node.text for node in section_chunks])

    # 长度保护，使用统一tokenizer接口
    def truncate_by_token(self, text: str, max_tokens: int) -> str:
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.tokenizer.decode(tokens[:max_tokens])

    def reconstruct_sections_to_text(
        self,
        vector_store: BaseVectorStore,
        hit_nodes: list[TextNode],
        max_context_tokens: int = 4096,
        section_separator: str = "\n---\n",
    ) -> str:
        """
        从召回节点列表中重构完整章节上下文

        Args:
            vector_store: 向量数据库实例
            hit_nodes: 召回的节点列表
            max_context_tokens: 最终上下文最大token数
            section_separator: 章节之间的分隔符

        Returns:
            重构后的上下文文本
        """
        if not hit_nodes:
            logger.warning("reconstruct_sections_to_text | hit_nodes 为空")
            return ""

        # 收集所有唯一 (file_md5, section_id) 章节对
        section_keys = self._extract_section_keys(hit_nodes)
        if not section_keys:
            logger.warning("reconstruct_sections_to_text | 未提取到有效的章节键")
            return ""

        # 批量获取所有章节的完整分片
        all_section_nodes = self._fetch_all_section_chunks(vector_store, section_keys)

        # 按章节分组并重构
        group_map = self._group_chunks_by_section(all_section_nodes)

        # 构建上下文：对每个章节合并，超长则摘要
        full_context_parts = self._build_section_contexts(group_map, section_keys)

        # 拼接并截断
        full_text = section_separator.join(full_context_parts)
        return self.truncate_by_token(full_text, max_context_tokens)

    def _extract_section_keys(self, nodes: list[TextNode]) -> set[tuple[str, str]]:
        """从节点列表中提取唯一的 (file_md5, section_id) 键"""
        section_keys = set()
        for node in nodes:
            file_md5 = node.metadata.get("file_md5")
            section_id = node.metadata.get("section_id")
            if file_md5 and section_id:
                section_keys.add((file_md5, section_id))
        return section_keys

    def _fetch_all_section_chunks(
        self, vector_store: BaseVectorStore, section_keys: set[tuple[str, str]]
    ) -> list[TextNode]:
        """批量获取所有章节的完整分片"""
        if not section_keys:
            return []

        # 构造 OR 查询条件
        or_conditions = []
        for file_md5, section_id in section_keys:
            or_conditions.append(
                {"$and": [{"file_md5": file_md5}, {"section_id": section_id}]}
            )
        batch_filter = {"$or": or_conditions}

        return vector_store.get_by_metadata(metadata_filter=batch_filter)

    def _group_chunks_by_section(
        self, chunks: list[TextNode]
    ) -> dict[tuple[str, str], list[TextNode]]:
        """按 (file_md5, section_id) 分组所有chunk分片"""
        group_map = {}
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

    def _build_section_contexts(
        self,
        group_map: dict[tuple[str, str], list[TextNode]],
        target_keys: set[tuple[str, str]],
    ) -> list[str]:
        """构建每个章节的上下文文本，超长则生成摘要"""
        contexts = []

        for key in target_keys:
            section_nodes = group_map.get(key, [])
            full_section = self._merge_chunks(section_nodes)
            if not full_section:
                continue

            # 检查是否需要摘要
            token_cnt = self.tokenizer.count_tokens(full_section)
            if token_cnt > self.section_summary_threshold and self.summarizer:
                logger.info(
                    f"需要summary | tokens={token_cnt} | threshold={self.section_summary_threshold}"
                )
                logger.info(
                    f"before:\n{full_section[:500]}..."
                )  # 只打印前500字符，避免日志太大
                compressed_text = self.summarizer.summarize(
                    text=full_section, max_summary_tokens=self.summary_max_tokens
                )
                logger.info(f"after:\n{compressed_text[:500]}...")
                contexts.append(compressed_text)
            else:
                contexts.append(full_section)

        return contexts

    def reconstruct_sections_to_nodes(
        self,
        vector_store: BaseVectorStore,
        hit_nodes: list[TextNode],
    ) -> list[TextNode]:
        """
        从召回节点，拉取完整章节分片，每个section_id合并成单个TextNode；
        章节文本token超过阈值则执行summary，返回List[TextNode]
        """
        if not hit_nodes:
            logger.warning("reconstruct_sections_to_nodes | hit_nodes 为空")
            return []

        # 收集所有唯一 (file_md5, section_id) 章节对
        section_keys = self._extract_section_keys(hit_nodes)
        if not section_keys:
            logger.warning("reconstruct_sections_to_nodes | 未提取到有效的章节键")
            return []

        # 批量获取所有章节的完整分片
        all_section_nodes = self._fetch_all_section_chunks(vector_store, section_keys)

        # 按章节分组
        group_map = self._group_chunks_by_section(all_section_nodes)

        # 1、先把每个section分片合并为完整章节Node（无摘要）
        full_nodes = self._build_section_nodes(group_map, section_keys)

        # 2、对合并后的章节，超长执行summary
        for node in full_nodes:
            token_cnt = self.tokenizer.count_tokens(node.text)
            if token_cnt > self.section_summary_threshold and self.summarizer:
                logger.info(
                    f"需要summary | tokens={token_cnt} | threshold={self.section_summary_threshold}"
                )
                logger.info(f"before:\n{node.text[:500]}...")
                compressed_text = self.summarizer.summarize(
                    text=node.text, max_summary_tokens=self.summary_max_tokens
                )
                logger.info(f"after:\n{compressed_text[:500]}...")
                node.text = compressed_text

        return full_nodes

    def _build_section_nodes(
        self,
        group_map: dict[tuple[str, str], list[TextNode]],
        target_keys: set[tuple[str, str]],
    ) -> list[TextNode]:
        """
        将同一个section_id下的多个分片chunk，合并成单个TextNode，**不做摘要**
        返回：每个章节对应一个合并完成的TextNode
        """
        from llama_index.core.schema import TextNode

        result_nodes = []
        for key in target_keys:
            section_nodes = group_map.get(key, [])
            if not section_nodes:
                continue
            # 按section_seq排序，拼接完整章节文本
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

    def merge_nodes_to_single_text(
        self,
        nodes: list[TextNode],
        max_context_tokens: int,
        section_separator: str = "\n---\n",
    ) -> str:
        """
        将多个TextNode文本拼接为单个完整文本；
        如果整体token超过max_context_tokens，执行全局摘要压缩至目标token。

        Args:
            nodes: 已经按章节合并完成的节点列表（来自 reconstruct_sections_to_nodes）
            max_context_tokens: 全局最大token上限，超过则整体summary
            section_separator: 章节之间的分隔符

        Returns:
            最终的上下文字符串
        """
        if not nodes:
            return ""

        # 1. 拼接全部章节
        parts = [n.text for n in nodes]
        full_text = section_separator.join(parts)

        # 2. 统计总token
        total_tokens = self.tokenizer.count_tokens(full_text)
        logger.info(
            f"merge_nodes_to_single_text | total_tokens={total_tokens}, max={max_context_tokens}"
        )

        # 没超限直接返回原文
        if total_tokens <= max_context_tokens:
            return full_text

        # 超限：有摘要器则全局摘要；没有就硬截断
        if self.summarizer is not None:
            logger.info(
                f"全局触发summary，总tokens={total_tokens}，压缩到 {max_context_tokens}"
            )
            logger.info(f"global summary before: {full_text[:600]}...")
            compressed = self.summarizer.summarize(
                text=full_text, max_summary_tokens=max_context_tokens
            )
            logger.info(f"global summary after: {compressed[:600]}...")
            return compressed
        else:
            # 无摘要器兜底：按token截断
            logger.warning("merge_nodes_to_single_text 无summarizer，执行硬token截断")
            return self.truncate_by_token(full_text, max_context_tokens)
