# app-server/src/com/damon/ming/ai/rag/index/index_text.py
"""构造用于向量与关键词索引的文本，不修改节点原文。"""

from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.rag.knowledge.metadata_keys import SOURCE_CONTEXT


def node_text_for_search(node: TextNode) -> str:
    source_context = node.metadata.get(SOURCE_CONTEXT)
    if source_context:
        return f"{source_context}\n{node.text}"
    return node.text
