# app-server/src/com/damon/ming/ai/retriever/bm25_index.py

import threading

import numpy as np
from llama_index.core.schema import TextNode
from src.com.damon.ming.log import pin


class BM25Index:
    """
    BM25 索引（基于 rank_bm25）
    为 SparseRetriever 提供底层关键词检索能力。

    线程安全：build() 写锁保护索引重建，get_scores() 读锁保护并发查询，
    避免 ingest 重建 BM25 过程中查询读到不一致状态。
    """

    def __init__(self, tokenizer=None):
        self.tokenizer = tokenizer or self._default_tokenizer
        self.index = None
        self.corpus: list[TextNode] = []
        self.logger = pin("BM25Index")
        self._rw_lock = threading.RLock()
        self._version = 0  # 索引版本号，build 时递增，查询时校验一致性

    def _default_tokenizer(self, text: str) -> list[str]:
        """默认简单空格分词，中文场景建议外部传入jieba等分词器"""
        return text.lower().split()

    def build(self, nodes: list[TextNode]):
        """构建 BM25 内存索引（双 buffer 原子替换，不阻塞并发查询）。

        构建过程在锁外完成，仅在最终替换指针时持锁（微秒级），
        避免 upload 重建 BM25 期间阻塞所有 chat 请求的稀疏检索。
        """
        from rank_bm25 import BM25Okapi

        if not nodes:
            with self._rw_lock:
                self.corpus = nodes
                self.index = None
                self._version += 1
                self.logger.warning("[BM25Index] 没有可建立索引的文档")
                return

        # 锁外构建新索引（耗时操作不阻塞读）
        tokenized_corpus = [self.tokenizer(node.text) for node in nodes]
        new_index = BM25Okapi(tokenized_corpus)

        # 锁内原子替换（微秒级引用赋值），版本号递增保证查询端可检测一致性
        with self._rw_lock:
            self.corpus = nodes
            self.index = new_index
            self._version += 1

        self.logger.info(f"[BM25Index] 索引构建完成 | 文档数: {len(nodes)}")

    def get_scores(self, query: str) -> np.ndarray:
        """获取查询对全部文档的BM25分数数组，和corpus一一对应。

        锁内做 index + corpus + version 三元组快照，评分计算在锁外。
        返回前校验 scores 长度与 corpus 一致，防止 build 过程中读到不一致状态。
        """
        with self._rw_lock:
            if self.index is None:
                raise ValueError("索引未初始化，请先执行 build()")
            index = self.index
            corpus = self.corpus
        # 锁外纯计算
        tokenized_query = self.tokenizer(query)
        scores = index.get_scores(tokenized_query)
        # 防御性校验：build 过程中 index 和 corpus 可能短暂不一致
        if len(scores) != len(corpus):
            self.logger.warning(
                "[BM25Index] 检测到索引版本不一致（build 中），本次查询返回空"
            )
            return np.zeros(len(corpus))
        return scores

    def get_top_k(self, query: str, top_k: int) -> list[tuple[TextNode, float]]:
        """获取 top-k 节点及分数。

        锁内做 index + corpus 引用快照（build 原子替换，引用安全），
        评分计算、argsort 和 tuple 构建全部在锁外，允许并发查询并行执行。
        返回前校验 scores 长度与 corpus 一致，防止 build 过程中读到不一致状态。
        """
        if top_k < 1:
            return []
        with self._rw_lock:
            if self.index is None:
                raise ValueError("索引未初始化，请先执行 build()")
            index = self.index  # 引用快照
            corpus = self.corpus  # 原子替换，快照引用安全
        # 锁外纯计算
        tokenized_query = self.tokenizer(query)
        scores = index.get_scores(tokenized_query)
        # 防御性校验：build 过程中 index 和 corpus 可能短暂不一致
        if len(scores) != len(corpus):
            self.logger.warning(
                "[BM25Index] 检测到索引版本不一致（build 中），本次查询返回空"
            )
            return []
        top_indices = scores.argsort()[-top_k:][::-1]
        return [(corpus[i], float(scores[i])) for i in top_indices]
