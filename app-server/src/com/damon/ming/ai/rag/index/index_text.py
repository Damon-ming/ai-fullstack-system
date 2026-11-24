# app-server/src/com/damon/ming/ai/rag/index/index_text.py
"""构造用于向量与关键词索引的文本，不修改节点原文。"""

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.rag.knowledge.metadata_keys import SOURCE_CONTEXT


def node_text_for_search(node: TextNode) -> str:
    # TODO: 用标注查询集对比启用/禁用 source_context 的 Recall@k、Precision@k，
    # 分别评估工作表名和幻灯片序号，再决定是否调整索引文本规则。
    source_context = node.metadata.get(SOURCE_CONTEXT)
    if source_context:
        return f"{source_context}\n{node.text}"
    return node.text
