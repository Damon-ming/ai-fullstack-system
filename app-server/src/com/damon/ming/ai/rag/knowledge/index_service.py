# app-server/src/com/damon/ming/ai/rag/knowledge/index_service.py
"""维护知识索引，并提供向量索引的应用层操作。"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from llama_index.core.schema import Document, TextNode
from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.index.index_text import node_text_for_search
from src.com.damon.ming.ai.rag.knowledge.bootstrap import (
    IndexSyncFailure,
    KnowledgeBootstrapResult,
)
from src.com.damon.ming.ai.rag.knowledge.metadata_keys import (
    FILE_ID,
    FILE_NAME,
    FILE_PATH,
    FILE_SHA256,
)
from src.com.damon.ming.ai.rag.retriever.bm25_index import BM25Index
from src.com.damon.ming.ai.rag.source.manager import DataSourceManager
from src.com.damon.ming.ai.rag.spliter.spliter import BaseDocumentSplitter
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.app.thread_pools import run_in_pool, submit_to_pool
from src.com.damon.ming.log import pin
from src.com.damon.ming.utils.time import now_iso

logger = pin("ai.knowledge_index")


class VectorIngestFailure(RuntimeError):
    """向量写入事务明确失败，没有确认成功的入库结果。"""


class KnowledgeIndexService:
    def __init__(
        self,
        *,
        corpus_dir: Path,
        document_pool: ThreadPoolExecutor,
        bm25_pool: ThreadPoolExecutor,
        splitter: BaseDocumentSplitter,
        embedder: BaseEmbeddingService,
        vector_store: BaseVectorStore,
        bm25_index: BM25Index,
        source_manager: DataSourceManager,
        bootstrap_result: KnowledgeBootstrapResult,
    ) -> None:
        self._corpus_dir = corpus_dir
        self._document_pool = document_pool
        self._bm25_pool = bm25_pool
        self._splitter = splitter
        self._embedder = embedder
        self._vector_store = vector_store
        self._bm25_index = bm25_index
        self._source_manager = source_manager
        # BM25 使用启动时的列表作为语料快照，上传在自己的列表上追加。
        self._nodes = list(bootstrap_result.nodes)
        self.startup_index_failures: list[IndexSyncFailure] = (
            bootstrap_result.index_failures
        )
        self.startup_discovered_file_paths: set[str] = (
            bootstrap_result.discovered_file_paths
        )

    def get_indexed_file_shas(self) -> set[str] | None:
        """读取已入库文件 SHA；查询失败时返回 None。"""
        return self._vector_store.get_distinct_metadata_values(FILE_SHA256)

    def get_indexed_file_paths_by_sha(self, file_sha256: str) -> list[str]:
        """读取指定 SHA 在向量元数据中记录的来源路径。"""
        nodes = self._vector_store.get_by_metadata({FILE_SHA256: file_sha256})
        return [
            str(node.metadata[FILE_PATH])
            for node in nodes
            if node.metadata.get(FILE_PATH)
        ]

    async def ingest_files(
        self,
        file_paths: list[str],
        file_id: str = "",
        disk_file_at: str = "",
        file_name: str = "",
    ) -> dict:
        """增量索引上传文件。向量写入失败时通知上传服务回滚。"""
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
                        FILE_SHA256: None,
                        FILE_PATH: str(path),
                        "reason": "parse_failed",
                    }
                )
                continue

            file_sha256 = docs[0].metadata.get(FILE_SHA256, "")
            try:
                nodes = await run_in_pool(
                    self._document_pool, self._splitter.split, docs
                )
            except asyncio.CancelledError:
                logger.warning("索引文件 | 文档分割阶段被取消")
                raise
            if nodes:
                parsed.append((nodes, file_sha256))

        for nodes, _ in parsed:
            embeddings = await run_in_pool(
                self._document_pool,
                self._embedder.embed_documents,
                [node_text_for_search(node) for node in nodes],
            )
            for node, embedding in zip(nodes, embeddings):
                node.embedding = embedding

        write_task = asyncio.create_task(
            run_in_pool(
                self._document_pool,
                self._write_files,
                parsed,
                skipped,
                file_id,
                disk_file_at,
                file_name,
            )
        )
        try:
            indexed, new_nodes, failed_count = await asyncio.shield(write_task)
        except asyncio.CancelledError:
            # 等待同步数据库事务结束后再把取消传给上传层执行补偿。
            try:
                await write_task
            except Exception:
                logger.exception("取消期间向量入库任务失败 | file_id=%s", file_id)
            raise
        self._nodes.extend(new_nodes)
        if failed_count:
            raise VectorIngestFailure(f"向量库入库事务失败，文件数: {failed_count}")

        if new_nodes:
            # BM25 全量重建交给单线程池，按提交顺序替换索引。
            snapshot = list(self._nodes)
            try:
                submit_to_pool(self._bm25_pool, self._bm25_index.build, snapshot)
                logger.info(
                    "BM25后台重建已提交 | 新增%d个节点，总节点数：%d",
                    len(new_nodes),
                    len(snapshot),
                )
            except Exception:
                # 向量库事务已提交；BM25 是派生索引，后台重建失败不回滚源数据。
                logger.exception("BM25后台重建提交失败")
        return {"indexed": indexed, "skipped": skipped}

    def update_file_path_by_sha(self, file_sha256: str, file_path: str | None) -> int:
        """修复向量库和内存 BM25 节点中的同 SHA 文件路径。"""
        updated = self._vector_store.update_metadata_by_filter(
            {FILE_SHA256: file_sha256},
            updates={FILE_PATH: file_path} if file_path is not None else None,
            remove_keys={FILE_PATH} if file_path is None else None,
        )
        for node in self._nodes:
            if node.metadata.get(FILE_SHA256) != file_sha256:
                continue
            if file_path is None:
                node.metadata.pop(FILE_PATH, None)
            else:
                node.metadata[FILE_PATH] = file_path
        if updated:
            snapshot = list(self._nodes)
            try:
                submit_to_pool(self._bm25_pool, self._bm25_index.build, snapshot)
            except Exception:
                logger.exception("路径修复后的 BM25 重建提交失败")
        return updated

    def delete_by_id(self, file_id: str) -> int:
        """删除本次上传的向量节点，并同步内存 BM25 语料。"""
        deleted = self._vector_store.delete_by_metadata({FILE_ID: file_id})
        if deleted:
            self._nodes = [
                node for node in self._nodes if node.metadata.get(FILE_ID) != file_id
            ]
            try:
                submit_to_pool(
                    self._bm25_pool,
                    self._bm25_index.build,
                    list(self._nodes),
                )
            except Exception:
                logger.exception("回滚后提交 BM25 重建失败 | file_id=%s", file_id)
        return deleted

    def remove_source_paths(self, file_paths: set[str]) -> int:
        """从内存节点和 BM25 语料移除对应磁盘路径。"""
        normalized_paths = {str(Path(path).resolve()) for path in file_paths}
        previous_count = len(self._nodes)
        self._nodes = [
            node
            for node in self._nodes
            if not node.metadata.get(FILE_PATH)
            or str(Path(node.metadata[FILE_PATH]).resolve()) not in normalized_paths
        ]
        removed_count = previous_count - len(self._nodes)
        if removed_count:
            self._bm25_index.build(list(self._nodes))
        return removed_count

    async def _load_documents(self, file_paths: list[str]) -> dict[str, list[Document]]:
        docs_by_path: dict[str, list[Document]] = {}
        try:
            docs = await run_in_pool(
                self._document_pool,
                self._source_manager.load_files,
                file_paths,
            )
        except asyncio.CancelledError:
            logger.warning("索引文件 | 数据源解析阶段被取消")
            raise
        for doc in docs:
            # e.g. "E:/knowledge/report.pdf": [doc1, doc2, doc3]
            docs_by_path.setdefault(doc.metadata[FILE_PATH], []).append(doc)
        return docs_by_path

    def _write_files(
        self,
        parsed: list[tuple[list[TextNode], str]],
        skipped: list[dict],
        file_id: str,
        disk_file_at: str,
        file_name: str,
    ) -> tuple[list[dict], list[TextNode], int]:
        indexed: list[dict] = []
        new_nodes: list[TextNode] = []
        failed_count = 0

        for nodes, file_sha256 in parsed:
            existing_nodes = self._vector_store.get_by_metadata(
                {FILE_SHA256: file_sha256}
            )
            if existing_nodes:
                stored_path = next(
                    (
                        str(node.metadata[FILE_PATH])
                        for node in existing_nodes
                        if node.metadata.get(FILE_PATH)
                    ),
                    None,
                )
                existing_path = next(
                    (
                        Path(node.metadata[FILE_PATH])
                        for node in existing_nodes
                        if node.metadata.get(FILE_PATH)
                        and Path(node.metadata[FILE_PATH]).is_file()
                    ),
                    None,
                )
                skipped.append(
                    {
                        FILE_SHA256: file_sha256,
                        "reason": "already_indexed",
                        "existing_file_path": str(existing_path)
                        if existing_path
                        else None,
                        "stored_file_path": stored_path,
                    }
                )
                continue

            indexed_at = now_iso()
            for node in nodes:
                if file_id:
                    node.metadata[FILE_ID] = file_id
                if file_name:
                    node.metadata[FILE_NAME] = file_name
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

            indexed.append({FILE_SHA256: file_sha256, "chunks": len(nodes)})
            new_nodes.extend(nodes)

        return indexed, new_nodes, failed_count
