# app-server/src/com/damon/ming/ai/rerank/cross_encoder_reranker.py

import torch
from llama_index.core.schema import TextNode
from src.com.damon.ming.ai.rerank import register_reranker
from src.com.damon.ming.ai.rerank.base_reranker import (
    BaseReranker,
    RerankerParams,
)
from src.com.damon.ming.log import pin


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

    def score_pairs(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []

        all_scores = []
        # 分批推理，避免OOM
        for start in range(0, len(texts), self.batch_size):
            batch_texts = texts[start : start + self.batch_size]
            pairs = [[query, text] for text in batch_texts]

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
        self, query: str, nodes: list[TextNode], top_k: int | None = None
    ) -> list[TextNode]:
        if not nodes:
            return []

        texts = [node.text for node in nodes]
        scores = self.model.score_pairs(query, texts)

        node_with_score = list(zip(nodes, scores))
        node_with_score.sort(key=lambda x: x[1], reverse=True)

        out_nodes = []
        for node, score in node_with_score:
            node.metadata["_rerank_score"] = float(score)
            out_nodes.append(node)

        if top_k is not None:
            out_nodes = out_nodes[:top_k]

        self.logger.info(f"[Rerank] 候选数量:{len(nodes)} → 输出:{len(out_nodes)}")
        return out_nodes
