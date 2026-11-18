"""从知识库磁盘数据构建内存检索节点并同步通用向量索引。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.com.damon.ming.ai.metadata_keys import FILE_PATH, FILE_SHA256
from src.com.damon.ming.ai.source import list_engines, resolve_source
from src.com.damon.ming.log import pin

if TYPE_CHECKING:
    from llama_index.core.schema import Document, TextNode
    from src.com.damon.ming.ai.embedding.BaseEmbeddingService import (
        BaseEmbeddingService,
    )
    from src.com.damon.ming.ai.retriever.bm25_index import BM25Index
    from src.com.damon.ming.ai.spliter.spliter import BaseDocumentSplitter
    from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore


logger = pin("ai.knowledge_bootstrap")


@dataclass(frozen=True)
class IndexSyncFailure:
    """同一内容（SHA）的一个或多个磁盘副本补录失败结果。"""

    file_sha256: str
    # 同 SHA 的并发/中断上传副本可能分布在不同路径；恢复逻辑需要逐个核对。
    file_paths: tuple[str, ...]
    error: str


@dataclass(frozen=True)
class KnowledgeBootstrapResult:
    """AI 启动所需节点及向量同步结果，不包含上传审计策略。"""

    nodes: list[TextNode]
    discovered_file_paths: set[str]
    index_failures: list[IndexSyncFailure]


def bootstrap_knowledge_index(
    *,
    knowledge_dir: Path,
    splitter: BaseDocumentSplitter,
    bm25_index: BM25Index,
    embedder: BaseEmbeddingService,
    vector_store: BaseVectorStore,
) -> KnowledgeBootstrapResult:
    """扫描数据源，重建 BM25 并对账 vector_db。"""
    documents: list[Document] = []
    for source_name in list_engines():
        source = resolve_source(source_name)(knowledge_dir)
        documents.extend(source.load_documents())

    discovered_file_paths = {
        str(Path(doc.metadata[FILE_PATH]).resolve())
        for doc in documents
        if doc.metadata.get(FILE_PATH)
    }
    nodes = splitter.split(documents)
    failures = _sync_vector_index(nodes, embedder, vector_store)
    if nodes:
        bm25_index.build(nodes)

    return KnowledgeBootstrapResult(
        nodes=nodes,
        discovered_file_paths=discovered_file_paths,
        index_failures=failures,
    )


def _sync_vector_index(
    nodes: list[TextNode],
    embedder: BaseEmbeddingService,
    vector_store: BaseVectorStore,
) -> list[IndexSyncFailure]:
    # 磁盘数据是知识库原始来源；该层只维护通用的磁盘与向量索引对账。
    db_shas = vector_store.get_distinct_metadata_values(FILE_SHA256)
    if db_shas is None:
        logger.warning("向量库 file_sha256 查询失败，跳过启动对账")
        return []
    if not db_shas and vector_store.count() > 0:
        logger.warning("向量库无 file_sha256 元数据，跳过启动对账")
        return []

    disk_shas = {
        node.metadata[FILE_SHA256] for node in nodes if node.metadata.get(FILE_SHA256)
    }
    for file_sha256 in db_shas - disk_shas:
        deleted = vector_store.delete_by_metadata({FILE_SHA256: file_sha256})
        logger.info(
            "启动对账：清理磁盘无源文件的向量索引 | sha=%s | chunks=%d",
            file_sha256[:16],
            deleted,
        )

    missing_shas = disk_shas - db_shas
    if not missing_shas:
        return []

    nodes_by_sha: dict[str, list[TextNode]] = defaultdict(list)
    for node in nodes:
        file_sha = node.metadata.get(FILE_SHA256)
        if file_sha in missing_shas:
            nodes_by_sha[file_sha].append(node)

    failures: list[IndexSyncFailure] = []
    logger.warning("启动对账：%d 个磁盘文件未入向量库，自动补录", len(missing_shas))
    for file_sha in missing_shas:
        file_nodes = nodes_by_sha.get(file_sha, [])
        try:
            _write_vectors(file_nodes, embedder, vector_store)
        except Exception as exc:
            # commit 返回异常时先确认结果，避免把已提交记录误判成孤立磁盘文件。
            current_shas = vector_store.get_distinct_metadata_values(FILE_SHA256)
            if current_shas is not None and file_sha in current_shas:
                logger.warning(
                    "启动补录抛错但 SHA 已存在于 vector_db，按已提交处理 | sha=%s",
                    file_sha[:16],
                )
                continue

            failures.append(
                IndexSyncFailure(
                    file_sha256=file_sha,
                    file_paths=tuple(
                        sorted(
                            {
                                str(Path(node.metadata[FILE_PATH]).resolve())
                                for node in file_nodes
                                if node.metadata.get(FILE_PATH)
                            }
                        )
                    ),
                    error=str(exc),
                )
            )
            logger.exception(
                "启动向量补录失败 | sha=%s",
                file_sha[:16],
            )
    return failures


def _write_vectors(
    nodes: list[TextNode],
    embedder: BaseEmbeddingService,
    vector_store: BaseVectorStore,
) -> None:
    if not nodes:
        return
    embeddings = embedder.embed_documents([node.text for node in nodes])
    for node, embedding in zip(nodes, embeddings):
        node.embedding = embedding
    vector_store.add_documents(nodes)
