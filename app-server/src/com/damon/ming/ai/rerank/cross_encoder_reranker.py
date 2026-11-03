# app-server/src/com/damon/ming/ai/rerank/cross_encoder_reranker.py

import copy
import threading

import torch
from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.rerank import register_reranker
from src.com.damon.ming.ai.rerank.base_reranker import (
    BaseReranker,
    RerankerParams,
)
from src.com.damon.ming.log import pin


def _uniform_sample(items: list[str], k: int) -> list[str]:
    """从列表中均匀采样 k 个元素，保留首尾。用于窗口数超上限时的降级。"""
    n = len(items)
    if k >= n:
        return items
    if k <= 1:
        return [items[0]]
    indices = [round(i * (n - 1) / (k - 1)) for i in range(k)]
    return [items[i] for i in indices]


class CrossEncoderModel:
    """
    CrossEncoder 底层推理封装
    只实现：query + 文本列表 → 相似度分数列表
    不感知业务框架、TextNode，可独立复用
    """

    def __init__(self, params: RerankerParams):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.logger = pin("CrossEncoderModel")

        device = params.device
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.logger.info(f"device: {device}")
        self.device = torch.device(device)
        self.max_seq_len = params.max_seq_len
        self.batch_size = params.batch_size

        self.logger.info(
            f"加载Rerank模型: {params.model_name}, device={self.device}, max_seq_len={params.max_seq_len}"
        )
        self.tokenizer = AutoTokenizer.from_pretrained(params.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            params.model_name
        )
        self.model.to(self.device)
        self.model.eval()
        # PyTorch 模型推理非线程安全，加锁串行化多线程并发 rerank
        self._infer_lock = threading.Lock()

    def score_pairs(
        self,
        query: str,
        texts: list[str],
        cancel_event: threading.Event | None = None,
    ) -> list[float]:
        if not texts:
            return []

        all_scores = []
        # 分批推理，避免OOM；每个 batch 独立持锁，允许 rerank 线程交替使用 GPU
        for start in range(0, len(texts), self.batch_size):
            # 协作取消：批次之间检查信号，已取消则放弃剩余批次
            if cancel_event is not None and cancel_event.is_set():
                return []
            batch_texts = texts[start : start + self.batch_size]
            pairs = [[query, text] for text in batch_texts]

            # 锁内：tokenizer + GPU 推理（PyTorch 线程安全要求）
            with self._infer_lock:
                inputs = self.tokenizer(
                    pairs,
                    padding=True,
                    truncation=True,
                    max_length=self.max_seq_len,
                    return_tensors="pt",
                ).to(self.device)

                with torch.no_grad():
                    outputs = self.model(**inputs)
                    scores = outputs.logits[:, 0].float()

            # 锁外：CPU 后处理（numpy 转换不依赖 GPU，可并发）
            all_scores.extend(scores.cpu().numpy().tolist())
        return all_scores


@register_reranker("cross_encoder")
class CrossEncoderReranker(BaseReranker):
    """
    CrossEncoder 重排适配器
    实现BaseReranker抽象接口，适配整套RAG框架
    """

    def __init__(self, params: RerankerParams):
        super().__init__(params)
        self.logger = pin("CrossEncoderReranker")
        self.model = CrossEncoderModel(params=params)

    def rerank(
        self,
        query: str,
        nodes: list[TextNode],
        top_k: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[TextNode]:
        if not nodes:
            return []

        # 长节点滑动窗口展开：每个 node → 1+ 个窗口文本
        # include_heading 开启时打分文本附带章节标题链，让 reranker 感知上下文层级
        all_texts: list[str] = []
        node_window_counts: list[int] = []
        for node in nodes:
            prefix = self._heading_prefix(node)
            windows = self._split_into_windows(query, node.text, prefix)
            node_window_counts.append(len(windows))
            all_texts.extend(windows)

        # score_pairs 内部持 _infer_lock 保护 PyTorch 推理，返回后锁已释放
        scores = self.model.score_pairs(query, all_texts, cancel_event)

        # 取消时 score_pairs 返回空列表，直接短路
        if not scores:
            return []

        # 按 node 聚合窗口分数（取 max）：任一部分高度相关即认为 node 相关
        node_scores: list[float] = []
        idx = 0
        for count in node_window_counts:
            node_scores.append(max(scores[idx : idx + count]))
            idx += count

        # 锁外排序 + deepcopy：nodes 是 rerank() 局部参数，RAGContainer 顺序调用，
        # 执行期间不会并发修改这些节点对象，锁外操作安全。
        scored_pairs = sorted(
            zip(nodes, node_scores),
            key=lambda x: x[1],
            reverse=True,
        )

        out_nodes = []
        for node, score in scored_pairs:
            # deepcopy 节点 + 写分数，避免并发写共享 TextNode 对象
            node = copy.deepcopy(node)
            node.metadata["_rerank_score"] = float(score)
            out_nodes.append(node)

        if top_k is not None:
            out_nodes = out_nodes[:top_k]

        self.logger.info(
            f"[Rerank] 候选数量:{len(nodes)} | 窗口总数:{len(all_texts)} → 输出:{len(out_nodes)}"
        )
        return out_nodes

    # ── 滑动窗口 ────────────────────────────────────────────────────────

    def _heading_prefix(self, node: TextNode) -> str:
        """构造章节标题链前缀。

        include_heading 由 YAML 显式控制；无 heading_path 的文档（如 PDF）
        返回空串，打分输入与原来完全一致。
        """
        if not self.params.include_heading:
            return ""
        heading = node.metadata.get("heading_path", "")
        if not heading:
            return ""
        clean = heading.strip("/").replace("/", " > ")
        return f"【{clean}】\n"

    def _split_into_windows(self, query: str, text: str, prefix: str) -> list[str]:
        """将长文本切分为滑动窗口，短文本直接返回原文。

        prefix（章节标题链）附加到每个窗口，保证各窗口打分语境一致；
        从窗口预算中扣除 prefix 的 token，避免超出 max_seq_len 被截断。
        window_overlap=0 时退化为整段返回（由 score_pairs 内部 truncate 兜底）。
        """
        if self.params.window_overlap <= 0:
            return [f"{prefix}{text}"] if prefix else [text]

        prefix_tokens = (
            len(self.model.tokenizer.encode(prefix, add_special_tokens=False))
            if prefix
            else 0
        )
        window_size = max(self._compute_window_size(query) - prefix_tokens, 1)
        token_ids = self.model.tokenizer.encode(text, add_special_tokens=False)

        if len(token_ids) <= window_size:
            return [f"{prefix}{text}"] if prefix else [text]

        step = max(window_size - self.params.window_overlap, 1)
        windows: list[str] = []
        for start in range(0, len(token_ids), step):
            end = min(start + window_size, len(token_ids))
            windows.append(
                f"{prefix}{self.model.tokenizer.decode(token_ids[start:end])}"
            )
            if end >= len(token_ids):
                break

        # 安全上限：窗口数超限时均匀采样，保留首尾覆盖
        max_windows = self.params.max_windows_per_node
        if len(windows) > max_windows:
            self.logger.warning(
                f"[Rerank] 窗口数超限降级 | section_tokens:{len(token_ids)} | "
                f"原始窗口数:{len(windows)} | 上限:{max_windows} | 已均匀采样保留首尾"
            )
            windows = _uniform_sample(windows, max_windows)
        return windows

    def _compute_window_size(self, query: str) -> int:
        """计算窗口 token 数：max_seq_len 扣除 query 和 special tokens。"""
        query_tokens = len(self.model.tokenizer.encode(query, add_special_tokens=False))
        # [CLS] + query + [SEP] + document + [SEP]
        return max(self.params.max_seq_len - query_tokens - 3, 1)
