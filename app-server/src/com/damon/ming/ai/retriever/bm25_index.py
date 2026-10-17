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

    def _default_tokenizer(self, text: str) -> list[str]:
        """默认简单空格分词，中文场景建议外部传入jieba等分词器"""
        return text.lower().split()

    def build(self, nodes: list[TextNode]):
        """构建 BM25 内存索引（写锁保护，阻塞并发查询）"""
        from rank_bm25 import BM25Okapi

        with self._rw_lock:
            self.corpus = nodes
            if not nodes:
                self.index = None
                self.logger.warning("[BM25Index] 没有可建立索引的文档")
                return
            tokenized_corpus = [self.tokenizer(node.text) for node in nodes]
            self.index = BM25Okapi(tokenized_corpus)
            self.logger.info(f"[BM25Index] 索引构建完成 | 文档数: {len(nodes)}")

    def get_scores(self, query: str) -> np.ndarray:
        """获取查询对全部文档的BM25分数数组，和corpus一一对应（读锁保护）"""
        with self._rw_lock:
            if self.index is None:
                raise ValueError("索引未初始化，请先执行 build()")
            tokenized_query = self.tokenizer(query)
            return self.index.get_scores(tokenized_query)
