# app-server/src/com/damon/ming/ai/rag/rag_tool.py
"""
RAG 容器 —— 检索线程编排层。

职责：
  - 编排 AI 模块的执行顺序（检索 → 重构 → rerank → 拼接 → 全局摘要）
  - 使用外层授予的 RAG 线程池能力，不接触其他资源组
  - vector DB 写入、删除和索引对账由 KnowledgeIndexService 提供
  - 取消由 asyncio.CancelledError 穿透所有 await 层，无需手动检查
  - AI 模块本身不感知线程/取消

检索取消策略：
  - asyncio task 取消通过 await 链传播；cancel_event 通知线程任务协作停止
  - 任意 await 点立即抛出 CancelledError，外层 catch 后 re-raise
  - 中断时直接抛弃内存中的中间数据（clones、压缩结果等），不做任何保存/恢复
  - 不碰 vector_db 中的原始数据

线程模型：
  - 全局线程预算由 app/config/thread 控制，RAG 内部池分配由 thread_pools/config 控制
  - 所属组件通过 RAG 线程池接口获取本组件需要的池
  - 异步 AI 函数（SummaryService.run_summary）直接调用
"""

import asyncio
import threading
from pathlib import Path

from src.com.damon.ming.ai.inference.inference_gateway import InferenceGateway
from src.com.damon.ming.ai.rag.constructor.constructor import SectionReconstructor
from src.com.damon.ming.ai.rag.embedding import (
    EmbeddingGateway,
)
from src.com.damon.ming.ai.rag.knowledge.bootstrap import bootstrap_knowledge_index
from src.com.damon.ming.ai.rag.knowledge.index_service import KnowledgeIndexService
from src.com.damon.ming.ai.rag.rerank import create_rerankers
from src.com.damon.ming.ai.rag.rerank.base_reranker import BaseReranker
from src.com.damon.ming.ai.rag.retriever import create_retrievers
from src.com.damon.ming.ai.rag.retriever.bm25_index import BM25Index
from src.com.damon.ming.ai.rag.spliter import create_splitters
from src.com.damon.ming.ai.rag.summary import create_summary_service
from src.com.damon.ming.ai.rag.thread_pools import RagThreadPools
from src.com.damon.ming.ai.rag.tokenizer import create_tokenizers
from src.com.damon.ming.ai.rag.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.ai.vector_db import BaseVectorStore, create_vector_stores
from src.com.damon.ming.app.thread_pools import run_in_pool
from src.com.damon.ming.log import pin
from src.com.damon.ming.thread import ThreadPoolGroup

logger = pin("ai.rag")

_rag_choreographer_instance = None
_rag_choreographer_lock = threading.Lock()


def get_rag_choreographer(
    pools: ThreadPoolGroup,
    corpus_dir: str,
    model_root_dir: str,
    inference_gateway: InferenceGateway,
    embedding_gateway: EmbeddingGateway,
):
    """进程级单例，上传和聊天共用同一个向量库/BM25实例。

    Args:
        pools: 仅限 RAG 资源组的线程池能力，由 AppInitializer 注入。
        corpus_dir: 知识库语料目录绝对路径（由 app.config 注入，必填）。
        model_root_dir: 本地模型统一目录（由 RagRuntime 环境配置注入）。
        inference_gateway: 启动时装配的统一推理入口（必填）。
        embedding_gateway: 启动时装配的统一 embedding 入口（必填）。
    """
    global _rag_choreographer_instance
    if _rag_choreographer_instance is None:
        with _rag_choreographer_lock:
            if _rag_choreographer_instance is None:
                _rag_choreographer_instance = RagChoreographer(
                    pools=pools,
                    corpus_dir=corpus_dir,
                    model_root_dir=model_root_dir,
                    inference_gateway=inference_gateway,
                    embedding_gateway=embedding_gateway,
                )
    return _rag_choreographer_instance


# 1. 全局单例容器
class RagChoreographer:
    def __init__(
        self,
        pools: ThreadPoolGroup,
        corpus_dir: str = "",
        model_root_dir: str = "",
        inference_gateway: InferenceGateway | None = None,
        embedding_gateway: EmbeddingGateway | None = None,
    ):
        logger.info("RAG 容器初始化开始")

        # 知识库目录：由 app.config 注入，不再硬编码，不合法直接抛异常
        if not corpus_dir:
            raise ValueError("RagChoreographer 初始化失败：corpus_dir 不能为空")
        corpus_path = Path(corpus_dir)

        if not model_root_dir:
            raise ValueError("RagChoreographer 初始化失败：model_root_dir 不能为空")
        model_root_path = Path(model_root_dir)

        if inference_gateway is None:
            raise ValueError("RagChoreographer 初始化失败：inference_gateway 不能为空")

        if embedding_gateway is None:
            raise ValueError("RagChoreographer 初始化失败：embedding_gateway 不能为空")

        self.thread_pools = RagThreadPools()
        self.thread_pools.initialize(pools)

        # 步骤1：使用 AppInitializer 装配并注入的 embedding gateway。
        self.embedding_gateway = embedding_gateway
        self.embedder = self.embedding_gateway.get_bge_m3()

        # 步骤2：加载通用 tokenizer，并注入 embedding 模型实际使用的 tokenizer
        self.tokenizer_manager = create_tokenizers(
            embedding_tokenizer=self.embedder.get_tokenizer()
        )
        self.llm_tokenizer: BaseTokenizer = self.tokenizer_manager.get_llm_tokenizer()
        # BM25 词语分词器（中文关键词检索）
        self.bm25_tokenizer = self.tokenizer_manager.get_bm25_tokenizer()
        embedding_tokenizer = (
            self.tokenizer_manager.get_embedding_tokenizer() or self.llm_tokenizer
        )

        # 步骤3：初始化向量库
        self.vector_store_manager = create_vector_stores()
        self._vector_store: BaseVectorStore = self.vector_store_manager.get_pgvector()

        # 步骤4：初始化章节重构 + 摘要服务
        self.section_recon = SectionReconstructor(
            self.thread_pools.get_retrieval_pool()
        )
        self.summary = create_summary_service(
            tokenizer=self.llm_tokenizer,
            summary_inference=inference_gateway.get_summary(),
        )

        # 步骤5：启动时加载 BGE-Reranker-v2-M3，避免首次请求时产生加载延迟
        self.reranker_manager = create_rerankers(model_root_path)
        self.reranker: BaseReranker = self.reranker_manager.get_bge_reranker_v2_m3()

        # 步骤6：BM25 索引由知识库和稀疏检索器共享。
        self.bm25_index = BM25Index(tokenizer=self.bm25_tokenizer.tokenize)
        self.retriever_manager = create_retrievers(
            vector_store=self._vector_store,
            embedder=self.embedder,
            bm25_index=self.bm25_index,
            retrieval_pool=self.thread_pools.get_retrieval_pool(),
        )
        self.retriever_config = self.retriever_manager.get_hybrid_config()
        self.hybrid_retriever = self.retriever_manager.get_hybrid()

        # 步骤7：初始化分割器

        self.splitter_manager = create_splitters(
            tokenizer=embedding_tokenizer,
            max_input_tokens=self.embedder.max_input_tokens,
        )
        self.splitter = self.splitter_manager.get_structured()

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

    async def build_rag_context(
        self,
        query: str,
        max_context_tokens: int,
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
        参数：
          - 候选池大小和最终输出大小均由 YAML 配置驱动，不再提供函数入参：
            retrieve_top_k — 检索器返回多少 section 给 reranker（候选池，决定 precision 上限）
            top_k          — reranker 精选后保留多少 section（最终上下文量级）

        Returns:
            检索结果文本。取消时抛出 asyncio.CancelledError。

        Raises:
            asyncio.CancelledError: 客户端断开或超时时向上传播。
        """
        cfg = self.retriever_config
        # 候选池大小（retrieve）与最终输出大小（rerank）分离，全部由 YAML 配置驱动：
        #   retrieve_top_k — 检索器返回多少 section 给 reranker（候选池，决定 precision 上限）
        #   top_k          — reranker 精选后保留多少 section（最终上下文量级）
        # TODO: 支持由外层调用参数动态传入 retrieve_top_k 和 rerank_top_k。
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

    def close(self) -> None:
        """关闭 RAG 持有的存储资源。"""
        self._vector_store.close()
        logger.info("RAG 向量存储已关闭")
