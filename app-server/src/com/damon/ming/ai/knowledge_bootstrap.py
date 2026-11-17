"""服务启动时从知识库目录恢复检索索引。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.com.damon.ming.ai.source import list_engines, resolve_source
from src.com.damon.ming.log import pin

if TYPE_CHECKING:
    from pathlib import Path

    from llama_index.core.schema import Document, TextNode
    from src.com.damon.ming.ai.embedding.BaseEmbeddingService import (
        BaseEmbeddingService,
    )
    from src.com.damon.ming.ai.retriever.bm25_index import BM25Index
    from src.com.damon.ming.ai.spliter.spliter import BaseDocumentSplitter
    from src.com.damon.ming.ai.vector_db.pgvector_store import PGVectorStore


logger = pin("ai.knowledge_bootstrap")


def bootstrap_knowledge_index(
    *,
    knowledge_dir: Path,
    splitter: BaseDocumentSplitter,
    bm25_index: BM25Index,
    embedder: BaseEmbeddingService,
    vector_store: PGVectorStore,
) -> list[TextNode]:
    """扫描已注册的数据源，重建 BM25 并同步向量库，返回内存节点。"""
    documents: list[Document] = []
    for source_name in list_engines():
        source = resolve_source(source_name)(knowledge_dir)
        documents.extend(source.load_documents())

    nodes = splitter.split(documents)
    if nodes:
        bm25_index.build(nodes)

    _sync_vector_index(nodes, embedder, vector_store)
    return nodes


def _sync_vector_index(
    nodes: list[TextNode],
    embedder: BaseEmbeddingService,
    vector_store: PGVectorStore,
) -> None:
    # 磁盘文件是原始来源。上传无法跨文件系统和数据库做原子事务，
    # 所以启动时补录缺失索引，并清理没有源文件的索引。
    if vector_store.count() == 0:
        _write_vectors(nodes, embedder, vector_store)
        return

    db_shas = vector_store.get_all_file_shas()
    if db_shas is None:
        logger.warning("向量库 file_sha256 查询失败，跳过启动对账")
        return
    if not db_shas:
        logger.warning("向量库无 file_sha256 元数据，跳过启动对账")
        return

    disk_shas = {
        node.metadata["file_sha256"]
        for node in nodes
        if node.metadata.get("file_sha256")
    }
    for file_sha256 in db_shas - disk_shas:
        deleted = vector_store.delete_by_metadata({"file_sha256": file_sha256})
        logger.info(
            "启动对账：清理磁盘无源文件的向量索引 | sha=%s | chunks=%d",
            file_sha256[:16],
            deleted,
        )

    missing_shas = disk_shas - db_shas
    if missing_shas:
        missing_nodes = [
            node for node in nodes if node.metadata.get("file_sha256") in missing_shas
        ]
        logger.warning("启动对账：%d 个磁盘文件未入向量库，自动补录", len(missing_shas))
        _write_vectors(missing_nodes, embedder, vector_store)


def _write_vectors(
    nodes: list[TextNode],
    embedder: BaseEmbeddingService,
    vector_store: PGVectorStore,
) -> None:
    if not nodes:
        return
    embeddings = embedder.embed_documents([node.text for node in nodes])
    for node, embedding in zip(nodes, embeddings):
        node.embedding = embedding
    vector_store.add_documents(nodes)
