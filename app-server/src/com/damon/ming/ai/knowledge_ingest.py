"""解析用户上传的文件并更新检索索引。"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from src.com.damon.ming.ai.source import list_engines, resolve_source
from src.com.damon.ming.app.thread_pools import run_in_pool, submit_to_pool
from src.com.damon.ming.log import pin
from src.com.damon.ming.utils.time import now_iso

if TYPE_CHECKING:
    from llama_index.core.schema import Document, TextNode
    from src.com.damon.ming.ai.embedding.BaseEmbeddingService import (
        BaseEmbeddingService,
    )
    from src.com.damon.ming.ai.retriever.bm25_index import BM25Index
    from src.com.damon.ming.ai.spliter.spliter import BaseDocumentSplitter
    from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
    from src.com.damon.ming.app.thread_pools import RagThreadPools
    from src.com.damon.ming.thread import CancellationToken


logger = pin("ai.knowledge_ingest")


class KnowledgeIngestService:
    def __init__(
        self,
        *,
        knowledge_dir: Path,
        thread_pools: RagThreadPools,
        splitter: BaseDocumentSplitter,
        embedder: BaseEmbeddingService,
        vector_store: BaseVectorStore,
        bm25_index: BM25Index,
        initial_nodes: list[TextNode],
    ) -> None:
        self._knowledge_dir = knowledge_dir
        self._document_pool = thread_pools.document
        self._bm25_pool = thread_pools.bm25
        self._splitter = splitter
        self._embedder = embedder
        self._vector_store = vector_store
        self._bm25_index = bm25_index
        # BM25 使用启动时的列表作为语料快照，上传在自己的列表上追加。
        self._nodes = list(initial_nodes)
        self._write_lock = threading.Lock()

    async def ingest_files(
        self,
        file_paths: list[str],
        cancellation_token: CancellationToken | None = None,
        file_uid: str = "",
        disk_file_at: str = "",
        file_name: str = "",
    ) -> dict:
        """增量索引上传文件。向量写入失败时通知上传服务回滚。"""
        if cancellation_token is not None:
            cancellation_token.register_task(asyncio.current_task())

        docs_by_path = await self._load_documents(file_paths)
        parsed: list[tuple[list[TextNode], str]] = []
        skipped: list[dict] = []
        for file_path in file_paths:
            path = Path(file_path).resolve()
            docs = docs_by_path.get(str(path))
            if not docs:
                logger.error("无法解析文件: %s", path.name)
                skipped.append(
                    {
                        "file_sha256": None,
                        "file_path": str(path),
                        "reason": "parse_failed",
                    }
                )
                continue

            file_sha256 = docs[0].metadata.get("file_sha256", "")
            try:
                nodes = await run_in_pool(
                    self._document_pool, self._splitter.split, docs
                )
            except asyncio.CancelledError:
                logger.warning("ingest_files | 文档分割阶段被取消")
                raise
            if nodes:
                parsed.append((nodes, file_sha256))

        for nodes, _ in parsed:
            embeddings = await run_in_pool(
                self._document_pool,
                self._embedder.embed_documents,
                [node.text for node in nodes],
            )
            for node, embedding in zip(nodes, embeddings):
                node.embedding = embedding

        indexed, new_nodes, failed_count = await run_in_pool(
            self._document_pool,
            self._write_files,
            parsed,
            skipped,
            file_uid,
            disk_file_at,
            file_name,
        )
        self._nodes.extend(new_nodes)
        if failed_count:
            raise RuntimeError(f"向量库入库失败，需回滚文件数: {failed_count}")

        if new_nodes:
            # BM25 全量重建交给单线程池，按提交顺序替换索引。
            snapshot = list(self._nodes)
            submit_to_pool(self._bm25_pool, self._bm25_index.build, snapshot)
            logger.info(
                "BM25后台重建已提交 | 新增%d个节点，总节点数：%d",
                len(new_nodes),
                len(snapshot),
            )
        return {"indexed": indexed, "skipped": skipped}

    async def _load_documents(self, file_paths: list[str]) -> dict[str, list[Document]]:
        docs_by_path: dict[str, list[Document]] = {}
        for source_name in list_engines():
            source = resolve_source(source_name)(self._knowledge_dir)
            try:
                docs = await run_in_pool(
                    self._document_pool, source.load_specific_files, file_paths
                )
            except asyncio.CancelledError:
                logger.warning("ingest_files | %s 加载阶段被取消", source_name)
                raise
            for doc in docs:
                docs_by_path.setdefault(doc.metadata["file_path"], []).append(doc)
        return docs_by_path

    def _write_files(
        self,
        parsed: list[tuple[list[TextNode], str]],
        skipped: list[dict],
        file_uid: str,
        disk_file_at: str,
        file_name: str,
    ) -> tuple[list[dict], list[TextNode], int]:
        indexed: list[dict] = []
        new_nodes: list[TextNode] = []
        failed_count = 0

        # 查重和写入必须共用一把锁，以免并发上传重复写入同一文件。
        with self._write_lock:
            for nodes, file_sha256 in parsed:
                if self._vector_store.get_by_metadata({"file_sha256": file_sha256}):
                    skipped.append(
                        {"file_sha256": file_sha256, "reason": "already_indexed"}
                    )
                    continue

                indexed_at = now_iso()
                for node in nodes:
                    if file_uid:
                        node.metadata["file_uid"] = file_uid
                    if file_name:
                        node.metadata["file_name"] = file_name
                    node.metadata["disk_file_at"] = disk_file_at
                    node.metadata["indexed_at"] = indexed_at

                try:
                    self._vector_store.add_documents(nodes)
                except Exception as exc:
                    logger.warning(
                        "向量库入库失败 | file_sha256=%s | error=%s",
                        file_sha256[:16],
                        exc,
                    )
                    failed_count += 1
                    continue

                indexed.append({"file_sha256": file_sha256, "chunks": len(nodes)})
                new_nodes.extend(nodes)

        return indexed, new_nodes, failed_count
