# app-server/src/com/damon/ming/ai/rag_tool.py

import threading
from pathlib import Path

from src.com.damon.ming.ai.constructor.constructor import SectionReconstructor
from src.com.damon.ming.ai.embedding.BaseEmbeddingService import BaseEmbeddingService
from src.com.damon.ming.ai.embedding.config import EmbeddingConfig
from src.com.damon.ming.ai.registry.db_registry import register_all_vector_dbs
from src.com.damon.ming.ai.registry.embedding_registry import register_all_embeddings
from src.com.damon.ming.ai.registry.rerank_registry import register_all_rerankers
from src.com.damon.ming.ai.registry.summary_registry import register_all_summarizers
from src.com.damon.ming.ai.registry.tokenizer_registry import register_all_tokenizers
from src.com.damon.ming.ai.rerank.config import RerankerConfig
from src.com.damon.ming.ai.retriever.base_retriever import (
    DenseRetriever,
    SparseRetriever,
)
from src.com.damon.ming.ai.retriever.bm25_index import BM25Index
from src.com.damon.ming.ai.retriever.hybrid_retriever import HybridRetriever
from src.com.damon.ming.ai.source.ref_sources import LocalPDFDataSource
from src.com.damon.ming.ai.spliter.spliter import MarkdownDocumentSplitter
from src.com.damon.ming.ai.summary import BaseSummarizer
from src.com.damon.ming.ai.summary.config import SummarizerConfig
from src.com.damon.ming.ai.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.ai.tokenizer.config import TokenizerConfig
from src.com.damon.ming.ai.vector_db.base_vector_db import BaseVectorStore
from src.com.damon.ming.ai.vector_db.config import VectorStoreConfig
from src.com.damon.ming.log import pin

logger = pin("ai.rag")

KNOWLEDGES_DIR = Path(__file__).resolve().parent.parent / "knowledges"
_rag_instance = None
_rag_instance_lock = threading.Lock()


def get_rag_container():
    """进程级单例，上传和聊天共用同一个向量库/BM25实例。"""
    global _rag_instance
    if _rag_instance is None:
        with _rag_instance_lock:
            if _rag_instance is None:
                _rag_instance = RAGContainer()
    return _rag_instance


# 1. 全局单例容器
class RAGContainer:
    def __init__(self):
        logger.info("RAG 容器初始化开始")
        # 步骤1：执行所有模块注册
        register_all_vector_dbs()
        register_all_embeddings()
        register_all_tokenizers()
        register_all_summarizers()
        register_all_rerankers()

        # 全局缓存全部分块节点，避免每次上传全量解析PDF
        self.all_nodes = []

        self.token_config = TokenizerConfig()
        self.tokenizer: BaseTokenizer = self.token_config.create_tokenizer(
            profile="default"
        )

        # 步骤2：加载配置，初始化Embedding
        self.emb_config = EmbeddingConfig()
        self.embedder: BaseEmbeddingService = self.emb_config.create_embedder(
            profile="default"
        )

        # 步骤3：初始化向量库（本地Chroma）
        self.vector_config = VectorStoreConfig()
        self.vector_store: BaseVectorStore = self.vector_config.create_store(
            profile="default"
        )

        # 新增：轻量文本摘要器
        self.summary_config = SummarizerConfig()
        self.summarizer: BaseSummarizer = self.summary_config.create_summarizer(
            profile="default"
        )

        # 步骤4：初始化章节重构工具（用于召回后合并完整章节）
        self.section_recon = SectionReconstructor(
            tokenizer=self.tokenizer, summarizer=self.summarizer
        )

        # 步骤5：初始化重排器 cross-encoder
        self.rerank_config = RerankerConfig()
        self.reranker = self.rerank_config.create_reranker(profile="default")

        # 步骤6：初始化稠密检索器
        self.dense_retriever = DenseRetriever(
            vector_store=self.vector_store, embedding_service=self.embedder
        )

        # 步骤7：初始化稀疏BM25索引（启动时预加载所有节点构建）
        self.bm25_index = BM25Index()
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

        # 文本切块器，补充缺失的分块逻辑
        self.splitter = MarkdownDocumentSplitter(
            tokenizer=self.tokenizer, max_chunk_token_size=1024, chunk_overlap=0
        )

        # 首次启动自动建立随项目发布的知识库，已有持久化数据时不重复写入。
        # 检查向量数据库中是否没有任何数据
        # 向量库负责持久化；BM25 是内存索引，服务每次启动只恢复 BM25。
        # 向量入库统一走 ingest_files，避免启动时重复 add_documents。
        docs = LocalPDFDataSource(KNOWLEDGES_DIR).load_documents()
        bm25_nodes = self.splitter.split(docs)
        self.all_nodes = bm25_nodes

        if bm25_nodes:
            self.bm25_index.build(bm25_nodes)

        if self.vector_store.count() == 0 and bm25_nodes:
            self._index_nodes(bm25_nodes, rebuild_bm25=False)
        elif self.vector_store.count() > 0:
            # 服务异常退出或人工拷贝了新 PDF 时，启动阶段补齐缺失向量；
            # ingest_files 会按 file_md5 跳过已经入库的文件。

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

    def ingest_files(self, file_paths: list[str]) -> dict:
        """增量处理上传文件，按 file_md5 保证本地文件和索引幂等。"""
        with self._knowledge_lock:
            accepted = []
            skipped = []
            # 只初始化一次数据源，不要循环内反复创建
            source_root = LocalPDFDataSource(KNOWLEDGES_DIR)
            upload_docs = source_root.load_specific_files(file_paths)

            # 构建 path -> docs 的映射，方便快速查找
            path_to_docs = {}
            for d in upload_docs:
                fp = d.metadata["file_path"]
                if fp not in path_to_docs:
                    path_to_docs[fp] = []
                path_to_docs[fp].append(d)

        new_nodes = []
        for file_path in file_paths:
            p = Path(file_path).resolve()
            key = str(p)
            docs = path_to_docs.get(key, [])
            if not docs:
                # 不抛异常，收集错误，跳过当前文件，继续下一个
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

            nodes = self.splitter.split(docs)
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

    def query_rag(self, query: str, top_k: int = 5, max_context_tokens: int = 4096):
        logger.info("RAG 检索开始 | query_length=%s | top_k=%s", len(query), top_k)
        # 1. 混合稠密+稀疏召回
        raw_nodes = self.hybrid_retriever.retrieve(
            query=query, top_k=top_k, dense_top_k=10, sparse_top_k=10
        )
        if not raw_nodes:
            logger.info("RAG 检索无结果")
            return ""

        # 3. 重构完整章节上下文（所有逻辑已封装到 SectionReconstructor）
        reconstructed_nodes = self.section_recon.reconstruct_sections_to_nodes(
            vector_store=self.vector_store,
            hit_nodes=raw_nodes,
        )

        # 2. CrossEncoder 重排过滤低相关文档
        rerank_nodes = self.reranker.rerank(
            query=query, nodes=reconstructed_nodes, top_k=top_k
        )
        if not rerank_nodes:
            logger.info("RAG 重排后无有效结果")
            return ""

        final_text = self.section_recon.merge_nodes_to_single_text(
            nodes=rerank_nodes, max_context_tokens=max_context_tokens
        )

        logger.info("RAG 检索完成 | context_length=%s", len(final_text))
        return final_text
