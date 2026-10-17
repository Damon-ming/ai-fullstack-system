# app-server/src/com/damon/ming/ai/rag_tool.py
"""
RAG 容器 —— 线程编排层 + 业务入口。

职责：
  - 编排 AI 模块的执行顺序（检索 → 重构 → 重排 → 压缩）
  - 管理线程池使用（将同步 AI 函数提交到 ThreadPoolManager）
  - 检查 CancellationToken，取消时停止提交新任务并清理
  - AI 模块本身不感知线程/取消

线程模型（executor 注入模式）：
  - RAGContainer 是 ThreadPoolManager 的唯一持有者
  - 同步 AI 函数通过 loop.run_in_executor(pool, fn, ...) 提交到线程池
  - AI 模块（HybridRetriever/SectionReconstructor）通过参数接收 executor 用于内部并行
  - 异步 AI 函数（SummaryService）直接调用，取消时 cancel 其 tasks
  - 每次操作前检查 cancellation_token，已取消则提前返回
"""

import asyncio
import threading
from pathlib import Path

from src.com.damon.ming.ai.config.embedding.embedding_config_loader import (
    EmbeddingConfigLoader,
)
from src.com.damon.ming.ai.config.inference.inference_config_loader import (
    InferenceConfigLoader,
)
from src.com.damon.ming.ai.config.rerank.rerank_config_loader import (
    RerankerConfigLoader,
)
from src.com.damon.ming.ai.config.tokenizer.tokenizer_config_loader import (
    TokenizerConfigLoader,
)
from src.com.damon.ming.ai.config.vector.vector_config_loader import VectorConfigLoader
from src.com.damon.ming.ai.constructor.constructor import SectionReconstructor
from src.com.damon.ming.ai.embedding.BaseEmbeddingService import BaseEmbeddingService
from src.com.damon.ming.ai.registry.embedding_registry import register_all_embeddings
from src.com.damon.ming.ai.registry.rerank_registry import register_all_rerankers
from src.com.damon.ming.ai.registry.tokenizer_registry import register_all_tokenizers
from src.com.damon.ming.ai.rerank.base_reranker import BaseReranker
from src.com.damon.ming.ai.retriever.base_retriever import (
    DenseRetriever,
    SparseRetriever,
)
from src.com.damon.ming.ai.retriever.bm25_index import BM25Index
from src.com.damon.ming.ai.retriever.hybrid_retriever import HybridRetriever
from src.com.damon.ming.ai.source.ref_sources import LocalPDFDataSource
from src.com.damon.ming.ai.spliter.spliter import MarkdownDocumentSplitter
from src.com.damon.ming.ai.summary import SummaryService
from src.com.damon.ming.ai.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.log import pin
from src.com.damon.ming.thread import CancellationToken, CancelResult, ThreadPoolManager

logger = pin("ai.rag")

KNOWLEDGES_DIR = Path(__file__).resolve().parent.parent / "knowledges"
_rag_instance = None
_rag_instance_lock = threading.Lock()


def get_rag_container(pool_mgr: ThreadPoolManager | None = None):
    """进程级单例，上传和聊天共用同一个向量库/BM25实例。

    Args:
        pool_mgr: 由 AppInitializer 注入的全局线程池管理器。
                  不为 None 时直接使用，否则退化为单例获取（向后兼容）。
    """
    global _rag_instance
    if _rag_instance is None:
        with _rag_instance_lock:
            if _rag_instance is None:
                _rag_instance = RAGContainer(pool_mgr=pool_mgr)
    return _rag_instance


# 1. 全局单例容器
class RAGContainer:
    def __init__(self, pool_mgr: ThreadPoolManager | None = None):
        logger.info("RAG 容器初始化开始")
        # 线程池管理器：优先使用注入的全局实例，否则回退单例
        self._pool_mgr = pool_mgr if pool_mgr is not None else ThreadPoolManager()
        # 步骤1：执行所有模块注册
        register_all_rerankers()
        register_all_tokenizers()
        register_all_embeddings()

        # 全局缓存全部分块节点，避免每次上传全量解析PDF
        self.all_nodes = []

        # 步骤1.5：全量加载所有分词器（启动时一次性加载，避免响应延迟）
        _tokenizers = TokenizerConfigLoader().load_all()
        self.tokenizer: BaseTokenizer = _tokenizers["llm_counter"]
        # BM25 词语分词器（中文关键词检索）
        self.word_tokenizer = _tokenizers["bm25_searcher"]
        # 所有分词器实例，外部按名字直接引用
        self.tokenizers = _tokenizers

        # 步骤2：全量加载所有 embedding（启动时一次性加载，避免响应延迟）
        _embedders = EmbeddingConfigLoader().load_all()
        self.embedder: BaseEmbeddingService = _embedders["ollama"]
        # 所有 embedding 实例，外部按名字直接引用
        self.embedders = _embedders

        # 步骤3：初始化向量库
        self.vector_store: BaseVectorStore = VectorConfigLoader().load("chroma")

        # 步骤4：初始化章节重构 + 摘要服务
        _infer_loader = InferenceConfigLoader()
        _infer_engine, _summary_entry = _infer_loader.get_engine_for_model("summary")
        self.section_recon = SectionReconstructor()
        self.summary = SummaryService(
            tokenizer=self.tokenizer,
            inference=_infer_engine,
            summary_model=_summary_entry.model_name,
            summary_options=_summary_entry.options,
        )

        # 步骤5：全量加载所有重排器（启动时一次性加载，避免响应延迟）
        self.rerankers: dict[str, BaseReranker] = RerankerConfigLoader().load_all()
        self.reranker: BaseReranker = self.rerankers["zh_primary"]

        # 步骤6：初始化稠密检索器
        self.dense_retriever = DenseRetriever(
            vector_store=self.vector_store, embedding_service=self.embedder
        )

        # 步骤7：初始化稀疏BM25索引（启动时预加载所有节点构建）
        self.bm25_index = BM25Index(tokenizer=self.word_tokenizer.tokenize)
        self._knowledge_lock = threading.RLock()
        self.sparse_retriever = SparseRetriever(bm25_index=self.bm25_index)

        # 步骤8：混合检索器（稠密+稀疏RRF融合）
        self.hybrid_retriever = HybridRetriever(
            dense_retriever=self.dense_retriever,
            sparse_retriever=self.sparse_retriever,
            dense_weight=0.7,
            sparse_weight=0.3,
            fuse_k=40,
        )

        # 文本切块器
        self.splitter = MarkdownDocumentSplitter(
            tokenizer=self.tokenizer, max_chunk_token_size=1024, chunk_overlap=0
        )

        # 首次启动自动建立知识库
        docs = LocalPDFDataSource(KNOWLEDGES_DIR).load_documents()
        bm25_nodes = self.splitter.split(docs)
        self.all_nodes = bm25_nodes

        if bm25_nodes:
            self.bm25_index.build(bm25_nodes)

        if self.vector_store.count() == 0 and bm25_nodes:
            self._index_nodes(bm25_nodes, rebuild_bm25=False)
        elif self.vector_store.count() > 0:
            pdf_paths = [str(path.resolve()) for path in KNOWLEDGES_DIR.rglob("*.pdf")]
            if pdf_paths:
                self.ingest_files(pdf_paths)

        logger.info("RAG 容器初始化完成")

    def _index_nodes(self, all_nodes, rebuild_bm25: bool = True) -> list[str]:
        """向量入库的唯一入口；调用方应确保节点已按 file_md5 去重。"""
        if not all_nodes:
            return []
        # 批量向量化
        texts = [n.text for n in all_nodes]
        embeddings = self.embedder.embed_documents(texts)
        for node, vec in zip(all_nodes, embeddings):
            node.embedding = vec

        # 写入向量库
        node_ids = self.vector_store.add_documents(all_nodes)
        # 刷新BM25
        if rebuild_bm25:
            self.bm25_index.build(all_nodes)
        return node_ids

    # ── ingest_files：上传线程编排 ────────────────────────────────────

    async def ingest_files(
        self,
        file_paths: list[str],
        cancellation_token: CancellationToken | None = None,
    ) -> dict:
        """增量处理上传文件。

        线程编排层：将同步的 PDF 加载和文档分割提交到线程池，
        定期检查取消令牌，已取消时停止处理并返回部分结果。
        """
        loop = asyncio.get_running_loop()
        pool_mgr = self._pool_mgr

        with self._knowledge_lock:
            accepted = []
            skipped = []
            source_root = LocalPDFDataSource(KNOWLEDGES_DIR)

            # 1. 提交 PDF 加载到线程池
            if cancellation_token is not None and cancellation_token.is_cancelled():
                logger.warning("ingest_files | 启动前检测到取消信号")
                return {"indexed": accepted, "skipped": skipped}

            # PDF 加载是 CPU 密集型，提交到 document 池
            document_pool = pool_mgr.get_pool("document")
            try:
                upload_docs = await loop.run_in_executor(
                    document_pool,
                    source_root.load_specific_files,
                    file_paths,
                )
            except asyncio.CancelledError:
                logger.warning("ingest_files | PDF 加载阶段被取消")
                raise

            # 构建 path -> docs 的映射
            path_to_docs = {}
            for d in upload_docs:
                fp = d.metadata["file_path"]
                if fp not in path_to_docs:
                    path_to_docs[fp] = []
                path_to_docs[fp].append(d)

        new_nodes = []
        for file_path in file_paths:
            # 检查取消信号
            if cancellation_token is not None and cancellation_token.is_cancelled():
                logger.warning(
                    f"ingest_files | 检测到取消信号，停止处理 | 已处理={len(accepted)}"
                )
                break

            p = Path(file_path).resolve()
            key = str(p)
            docs = path_to_docs.get(key, [])
            if not docs:
                logger.error(f"无法解析文件: {p.name}")
                skipped.append(
                    {
                        "file_md5": None,
                        "file_path": str(p),
                        "reason": "parse_failed",
                    }
                )
                continue

            file_md5 = docs[0].metadata.get("file_md5")
            existing = self.vector_store.get_by_metadata({"file_md5": file_md5})

            if existing:
                skipped.append({"file_md5": file_md5, "reason": "already_indexed"})
                continue

            # 提交文档分割到线程池
            try:
                nodes = await loop.run_in_executor(
                    document_pool,
                    self.splitter.split,
                    docs,
                )
            except asyncio.CancelledError:
                logger.warning("ingest_files | 文档分割阶段被取消")
                raise

            self._index_nodes(nodes, rebuild_bm25=False)
            accepted.append({"file_md5": file_md5, "chunks": len(nodes)})
            new_nodes.extend(nodes)

        # 只把本次新增节点追加到内存节点列表，然后用全部内存节点重建BM25
        if new_nodes:
            self.all_nodes.extend(new_nodes)
            self.bm25_index.build(self.all_nodes)
            logger.info(
                f"BM25增量更新完成，新增{len(new_nodes)}个节点，总节点数：{len(self.all_nodes)}"
            )
        return {"indexed": accepted, "skipped": skipped}

    # ── query_rag：检索线程编排 ────────────────────────────────────────

    async def query_rag(
        self,
        query: str,
        top_k: int = 5,
        max_context_tokens: int = 4096,
        cancellation_token: CancellationToken | None = None,
    ) -> str:
        """RAG 检索主流程。

        线程编排层（executor 注入模式）：
          1. HybridRetriever → 线程池注入，内部并行执行稠密+稀疏检索
          2. SectionReconstructor → 线程池注入，内部并发获取章节分片
          3. SummaryService.compress → 纯 asyncio，内部使用 create_task
          4. 每个阶段后检查取消信号，已取消则提前返回

        Executor 注入模式：
          - RAGContainer 是 ThreadPoolManager 的唯一使用者
          - AI 模块通过参数接收 executor，不创建/不持有线程池
          - 取消时 RAGContainer 只需取消 future，AI 模块无需感知

        Returns:
            检索结果文本。取消时返回空字符串。

        Raises:
            asyncio.CancelledError: 外部取消时向上传播。
        """
        # 取消追踪器 —— 精确记录到哪一步取消
        cancel_result = CancelResult()

        logger.info("RAG 检索开始 | query_length=%s | top_k=%s", len(query), top_k)

        loop = asyncio.get_running_loop()
        pool_mgr = self._pool_mgr

        # ── 阶段 1: 混合检索（线程池注入到模块内部，模块自行并行） ──
        # HybridRetriever 是同步函数，run_in_executor 提交到线程池避免阻塞事件循环。
        # executor=retrieval_pool 同时注入到模块内部，供稠密/稀疏并行使用。
        # 内部并行的两个子任务也在同一个池中执行，不额外占用外层线程。
        retrieval_pool = pool_mgr.get_pool("retrieval")

        if cancellation_token is not None and cancellation_token.is_cancelled():
            cancel_result.step = "before_retrieval"
            logger.info("RAG 检索取消 | %s", cancel_result.describe())
            return ""

        try:
            raw_nodes = await loop.run_in_executor(
                retrieval_pool,
                lambda: self.hybrid_retriever.retrieve(
                    query=query,
                    top_k=top_k,
                    dense_top_k=10,
                    sparse_top_k=10,
                    metadata_filter=None,
                    executor=retrieval_pool,
                ),
            )
        except asyncio.CancelledError:
            cancel_result.step = "hybrid_retrieval"
            logger.info("RAG 检索取消 | %s", cancel_result.describe())
            raise

        cancel_result.mark_completed("hybrid_retrieval")

        # 检查取消信号
        if cancellation_token is not None and cancellation_token.is_cancelled():
            cancel_result.step = "after_retrieval"
            logger.info("RAG 检索取消 | %s", cancel_result.describe())
            return ""

        if not raw_nodes:
            logger.info("RAG 检索无结果")
            return ""

        # ── 阶段 2: 章节重构（线程池注入，内部并发获取分片） ──
        try:
            reconstructed_nodes = (
                await self.section_recon.reconstruct_sections_to_nodes(
                    vector_store=self.vector_store,
                    hit_nodes=raw_nodes,
                    executor=retrieval_pool,  # 注入线程池，内部并发查 vector_store
                )
            )
        except asyncio.CancelledError:
            cancel_result.step = "section_reconstruct"
            logger.info("RAG 检索取消 | %s", cancel_result.describe())
            raise

        cancel_result.mark_completed("section_reconstruct")

        # 检查取消信号
        if cancellation_token is not None and cancellation_token.is_cancelled():
            cancel_result.step = "after_reconstruct"
            logger.info("RAG 检索取消 | %s", cancel_result.describe())
            return ""

        # ── 阶段 3: rerank 前压缩（SummaryService 内部并发 + 取消感知） ──
        max_seq_len = self.reranker.params.max_seq_len

        try:
            compress_result = await self.summary.compress_nodes_cancellable(
                reconstructed_nodes, max_seq_len, cancellation_token
            )
            if compress_result.was_cancelled():
                cancel_result.step = compress_result.step
                cancel_result.completed_steps.extend(compress_result.completed_steps)
                logger.info("RAG 检索取消 | %s", cancel_result.describe())
                return ""
        except asyncio.CancelledError:
            cancel_result.step = "compress_nodes"
            logger.info("RAG 检索取消 | %s", cancel_result.describe())
            raise

        cancel_result.mark_completed("compress_nodes")

        # ── 阶段 4: 重排 ──
        if cancellation_token is not None and cancellation_token.is_cancelled():
            cancel_result.step = "before_rerank"
            logger.info("RAG 检索取消 | %s", cancel_result.describe())
            return ""

        rerank_nodes = self.reranker.rerank(
            query=query, nodes=reconstructed_nodes, top_k=top_k
        )
        if not rerank_nodes:
            logger.info("RAG 重排后无有效结果")
            return ""

        cancel_result.mark_completed("rerank")

        # ── 阶段 5: 恢复原文 ──
        self.summary.restore_node_originals(rerank_nodes)

        # ── 阶段 6: 拼接 ──
        full_text = self.section_recon.merge_nodes_to_text(rerank_nodes)

        # ── 阶段 7: 全局超限摘要 ──
        total_tokens = self.summary.tokenizer.count_tokens(full_text)
        if total_tokens > max_context_tokens:
            if cancellation_token is not None and cancellation_token.is_cancelled():
                cancel_result.step = "before_summary"
                logger.info("RAG 检索取消 | %s", cancel_result.describe())
                return ""

            if self.summary.inference is not None:
                try:
                    full_text = await self.summary.run_summary_cancellable(
                        full_text, max_context_tokens, cancellation_token
                    )
                except asyncio.CancelledError:
                    cancel_result.step = "global_summary"
                    logger.info("RAG 检索取消 | %s", cancel_result.describe())
                    raise
            else:
                full_text = self.summary.truncate_by_token(
                    full_text, max_context_tokens
                )

        cancel_result.mark_completed("summary")
        logger.info("RAG 检索完成 | context_length=%s", len(full_text))
        return full_text
