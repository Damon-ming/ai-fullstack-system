# app-server/src/com/damon/ming/ai/rag_tool.py
"""
RAG 容器 —— 检索线程编排层。

职责：
  - 编排 AI 模块的执行顺序（检索 → 重构 → rerank → 拼接 → 全局摘要）
  - 使用外层授予的 RAG 线程池能力，不接触其他资源组
  - vector DB 写入、删除和索引对账由 KnowledgeIndexService 提供
  - 取消由 asyncio.CancelledError 穿透所有 await 层，无需手动检查
  - AI 模块本身不感知线程/取消

检索取消策略：
  - CancellationToken.register_task() 使 token.cancel() 直接取消当前 asyncio 协程
  - 任意 await 点立即抛出 CancelledError，外层 catch 后 re-raise
  - 中断时直接抛弃内存中的中间数据（clones、压缩结果等），不做任何保存/恢复
  - 不碰 vector_db 中的原始数据

线程模型：
  - 全局线程预算由 app/config/thread 控制，RAG 内部池分配由 ai/config/thread 控制
  - 所属组件通过 RAG 线程池接口获取本组件需要的池
  - 异步 AI 函数（SummaryService.run_summary）直接调用
"""

import asyncio
import threading
from pathlib import Path
from typing import cast

from src.com.damon.ming.ai.config.embedding.embedding_config_loader import (
    EmbeddingConfigLoader,
)
from src.com.damon.ming.ai.config.rerank.rerank_config_loader import (
    RerankerConfigLoader,
)
from src.com.damon.ming.ai.config.retriever.retriever_config_loader import (
    RetrieverConfigLoader,
)
from src.com.damon.ming.ai.config.splitter.splitter_config_loader import (
    SplitterConfigLoader,
)
from src.com.damon.ming.ai.config.tokenizer.tokenizer_config_loader import (
    TokenizerConfigLoader,
)
from src.com.damon.ming.ai.config.vector.vector_config_loader import VectorConfigLoader
from src.com.damon.ming.ai.constructor.constructor import SectionReconstructor
from src.com.damon.ming.ai.embedding.BaseEmbeddingService import BaseEmbeddingService
from src.com.damon.ming.ai.knowledge.bootstrap import bootstrap_knowledge_index
from src.com.damon.ming.ai.knowledge.index_service import KnowledgeIndexService
from src.com.damon.ming.ai.registry.embedding_registry import register_all_embeddings
from src.com.damon.ming.ai.registry.rerank_registry import register_all_rerankers
from src.com.damon.ming.ai.registry.source_registry import register_all_sources
from src.com.damon.ming.ai.registry.tokenizer_registry import register_all_tokenizers
from src.com.damon.ming.ai.rerank.base_reranker import BaseReranker
from src.com.damon.ming.ai.retriever.base_retriever import (
    DenseRetriever,
    SparseRetriever,
)
from src.com.damon.ming.ai.retriever.bm25_index import BM25Index
from src.com.damon.ming.ai.retriever.hybrid_retriever import HybridRetriever
from src.com.damon.ming.ai.spliter.spliter import MarkdownDocumentSplitter
from src.com.damon.ming.ai.summary import SummaryService
from src.com.damon.ming.ai.thread_pools import RagThreadPools
from src.com.damon.ming.ai.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.ai.vector_db.pgvector_store import PGVectorStore
from src.com.damon.ming.app.config.rag.rag_runtime_config_loader import (
    RagConfigLoader,
)
from src.com.damon.ming.app.thread_pools import run_in_pool
from src.com.damon.ming.log import pin
from src.com.damon.ming.thread import CancellationToken, ThreadPoolGroup

logger = pin("ai.rag")

_rag_instance = None
_rag_instance_lock = threading.Lock()


def get_rag_container(
    pools: ThreadPoolGroup,
    rag_sem: asyncio.Semaphore,
    corpus_dir: str,
    loader: RagConfigLoader,
):
    """进程级单例，上传和聊天共用同一个向量库/BM25实例。

    Args:
        pools: 仅限 RAG 资源组的线程池能力，由 AppInitializer 注入。
        rag_sem: RAG 流程共享的推理并发信号量（必填）。
        corpus_dir: 知识库语料目录绝对路径（由 app.config 注入，必填）。
        loader: 推理配置加载器（由 AppInitializer 注入，必填）。
    """
    global _rag_instance
    if _rag_instance is None:
        with _rag_instance_lock:
            if _rag_instance is None:
                _rag_instance = RAGContainer(
                    pools=pools,
                    rag_sem=rag_sem,
                    corpus_dir=corpus_dir,
                    loader=loader,
                )
    return _rag_instance


# 1. 全局单例容器
class RAGContainer:
    def __init__(
        self,
        pools: ThreadPoolGroup,
        rag_sem: asyncio.Semaphore,
        corpus_dir: str = "",
        loader: RagConfigLoader | None = None,
    ):
        logger.info("RAG 容器初始化开始")

        # 推理信号量：所有 LLM 调用（主推理 + 摘要 + 压缩）共享同一上限
        self._rag_sem = rag_sem

        # 知识库目录：由 app.config 注入，不再硬编码，不合法直接抛异常
        if not corpus_dir:
            raise ValueError("RAGContainer 初始化失败：corpus_dir 不能为空")
        corpus_path = Path(corpus_dir)

        # 推理配置加载器：由 AppInitializer 注入（全进程唯一实例）
        if loader is None:
            raise ValueError("RAGContainer 初始化失败：loader 不能为空")

        self.thread_pools = RagThreadPools()
        self.thread_pools.initialize(pools)

        # 步骤1：执行所有模块注册
        register_all_rerankers()
        register_all_tokenizers()
        register_all_embeddings()
        register_all_sources()

        # 步骤1.5：全量加载所有分词器（启动时一次性加载，避免响应延迟）
        _tokenizers = TokenizerConfigLoader().load_all()
        self.tokenizer: BaseTokenizer = _tokenizers["llm_counter"]
        # BM25 词语分词器（中文关键词检索）
        self.word_tokenizer = _tokenizers["bm25_searcher"]
        # 所有分词器实例，外部按名字直接引用
        self.tokenizers = _tokenizers

        # 步骤2：全量加载所有 embedding（启动时一次性加载，避免响应延迟）
        _embedders = EmbeddingConfigLoader().load_all()
        self.embedder: BaseEmbeddingService = _embedders["huggingface"]
        # 所有 embedding 实例，外部按名字直接引用
        self.embedders = _embedders

        # 步骤3：初始化向量库
        self._vector_store = cast(PGVectorStore, VectorConfigLoader().load("pgvector"))

        # 步骤4：初始化章节重构 + 摘要服务
        _summary_entry = loader.load().rag.roles["summary"]
        self.section_recon = SectionReconstructor(
            self.thread_pools.get_retrieval_pool()
        )
        self.summary = SummaryService(
            tokenizer=self.tokenizer,
            inference=_summary_entry.engine,
            summary_model=_summary_entry.model_name,
            summary_options=_summary_entry.options,
            semaphore=self._rag_sem,
        )

        # 步骤5：全量加载所有重排器（启动时一次性加载，避免响应延迟）
        self.rerankers: dict[str, BaseReranker] = RerankerConfigLoader().load_all()
        self.reranker: BaseReranker = self.rerankers["zh_primary"]

        # 步骤6：加载检索器配置（top_k/weights/fuse_k 全部由 YAML 驱动）
        _retriever_cfgs = RetrieverConfigLoader().load_all()
        self.retriever_config = _retriever_cfgs["common"]

        # 步骤7：初始化稠密检索器
        self.dense_retriever = DenseRetriever(
            vector_store=self._vector_store, embedding_service=self.embedder
        )

        # 步骤8：初始化稀疏BM25索引（启动时预加载所有节点构建）
        self.bm25_index = BM25Index(tokenizer=self.word_tokenizer.tokenize)
        self.sparse_retriever = SparseRetriever(bm25_index=self.bm25_index)

        # 步骤9：混合检索器（稠密+稀疏RRF融合，参数来自 YAML）
        self.hybrid_retriever = HybridRetriever(
            dense_retriever=self.dense_retriever,
            sparse_retriever=self.sparse_retriever,
            dense_weight=self.retriever_config.dense_weight,
            sparse_weight=self.retriever_config.sparse_weight,
            fuse_k=self.retriever_config.fuse_k,
            max_section_oversample_multiplier=self.retriever_config.max_section_oversample_multiplier,
            rrf_oversample_multiplier=self.retriever_config.rrf_oversample_multiplier,
            retrieval_pool=self.thread_pools.get_retrieval_pool(),
        )

        # 步骤10：加载分割器参数并构造切块器
        _splitter_cfgs = SplitterConfigLoader().load_all()
        self.splitter_config = _splitter_cfgs["common"]
        self.splitter = MarkdownDocumentSplitter(
            tokenizer=self.tokenizer,
            max_chunk_token_size=self.splitter_config.max_chunk_token_size,
            chunk_overlap=self.splitter_config.chunk_overlap,
        )

        bootstrap_result = bootstrap_knowledge_index(
            corpus_dir=corpus_path,
            splitter=self.splitter,
            bm25_index=self.bm25_index,
            embedder=self.embedder,
            vector_store=self._vector_store,
        )
        self.knowledge_index_service = KnowledgeIndexService(
            corpus_dir=corpus_path,
            document_pool=self.thread_pools.get_document_pool(),
            bm25_pool=self.thread_pools.get_bm25_pool(),
            splitter=self.splitter,
            embedder=self.embedder,
            vector_store=self._vector_store,
            bm25_index=self.bm25_index,
            bootstrap_result=bootstrap_result,
        )
        logger.info("RAG 容器初始化完成")

    # ── query_rag：检索线程编排 ────────────────────────────────────────

    async def query_rag(
        self,
        query: str,
        max_context_tokens: int,
        cancellation_token: CancellationToken | None = None,
    ) -> str:
        """RAG 检索主流程。

        线程编排层：
          1. 混合检索（HybridRetriever 使用 retrieval 池）
          2. 章节重构（SectionReconstructor 使用 retrieval 池）
          3. rerank 重排（长节点由 reranker 内部滑动窗口处理）
          4. 拼接
          5. 全局超限摘要（run_summary 或 truncate_by_token）
          6. 取消由 asyncio.CancelledError 统一处理——任何 await 点立即中断

        线程池由统一管理器统计和回收；组件通过 RAG 专属接口获取需要的池。
          - 取消时 CancelledError 穿透所有 await 层，无需手动检查

        取消联动：
          - cancellation_token.register_task(asyncio.current_task()) 使 token.cancel()
            能直接取消当前协程，实现毫秒级中断

        参数：
          - 候选池大小和最终输出大小均由 YAML 配置驱动，不再提供函数入参：
            retrieve_top_k — 检索器返回多少 section 给 reranker（候选池，决定 precision 上限）
            top_k          — reranker 精选后保留多少 section（最终上下文量级）

        Returns:
            检索结果文本。取消时抛出 asyncio.CancelledError。

        Raises:
            asyncio.CancelledError: 客户端断开或超时时向上传播。
        """
        # 注册当前 task → token.cancel() 可直接取消本协程
        if cancellation_token is not None:
            cancellation_token.register_task(asyncio.current_task())

        cfg = self.retriever_config
        # 候选池大小（retrieve）与最终输出大小（rerank）分离，全部由 YAML 配置驱动：
        #   retrieve_top_k — 检索器返回多少 section 给 reranker（候选池，决定 precision 上限）
        #   top_k          — reranker 精选后保留多少 section（最终上下文量级）
        retrieve_top_k = cfg.retrieve_top_k
        rerank_top_k = cfg.top_k

        logger.info(
            "RAG 检索开始 | query_length=%s | retrieve_top_k=%s | rerank_top_k=%s",
            len(query),
            retrieve_top_k,
            rerank_top_k,
        )

        # 协作取消信号：超时或客户端断开时通知线程池中的 rerank 提前退出
        cancel_event = threading.Event()

        try:
            # ── 阶段 1: 混合检索（参数全部来自 YAML 配置） ──
            # 传入 cancel_event，使稠密/稀疏检索之间可感知取消信号
            raw_nodes = await self.hybrid_retriever.retrieve(
                query=query,
                top_k=retrieve_top_k,
                dedup_by_section=cfg.dedup_by_section,
                dense_top_k=cfg.dense_top_k,
                sparse_top_k=cfg.sparse_top_k,
                metadata_filter=None,
                cancel_event=cancel_event,
            )
            if not raw_nodes:
                logger.info("RAG 检索无结果")
                return ""

            # ── 阶段 2: 章节重构 ──
            reconstructed_nodes = (
                await self.section_recon.reconstruct_sections_to_nodes(
                    vector_store=self._vector_store,
                    hit_nodes=raw_nodes,
                )
            )

            # ── 阶段 3: rerank 重排（CPU/GPU 密集，提交到独立 rerank 池） ──
            # 长节点由 reranker 内部滑动窗口处理（逐窗口打分取 max），无需预压缩。
            # 使用独立池避免 rerank 长耗时占用 retrieval 线程（与 Stage 1/2 隔离）
            # 传入 cancel_event，使 rerank 内部可在取消信号下提前退出
            ranked_nodes = await run_in_pool(
                self.thread_pools.get_rerank_pool(),
                self.reranker.rerank,
                query,
                reconstructed_nodes,
                rerank_top_k,
                cancel_event,
            )
            if not ranked_nodes:
                logger.info("RAG 重排后无有效结果")
                return ""

            # ── 阶段 4: 拼接 ──
            full_text = self.section_recon.merge_nodes_to_text(ranked_nodes)

            # ── 阶段 5: 全局超限摘要 ──
            total_tokens = self.summary.tokenizer.count_tokens(full_text)
            if total_tokens > max_context_tokens:
                full_text = await self.summary.run_summary(
                    full_text, max_context_tokens
                )
                # 摘要后仍超限则截断兜底
                if self.summary.tokenizer.count_tokens(full_text) > max_context_tokens:
                    logger.warning(
                        "全局摘要后仍超限 | 摘要tokens=%d | max=%d | 截断兜底",
                        self.summary.tokenizer.count_tokens(full_text),
                        max_context_tokens,
                    )
                    full_text = self.summary.truncate_by_token(
                        full_text, max_context_tokens
                    )

            logger.info("RAG 检索完成 | context_length=%s", len(full_text))
            return full_text

        except asyncio.CancelledError:
            # 通知线程池中的 rerank 提前退出，避免无效计算
            cancel_event.set()
            logger.warning("RAG 检索被取消（客户端断开）")
            raise
        except TimeoutError:
            # asyncio.timeout 触发时 CancelledError 会被转换为 TimeoutError，
            # 需在此单独设置 cancel_event，否则后台线程无法感知取消
            cancel_event.set()
            logger.warning("RAG 检索超时，通知后台线程停止")
            raise
