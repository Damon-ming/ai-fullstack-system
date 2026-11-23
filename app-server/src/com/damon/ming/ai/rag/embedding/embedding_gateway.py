# app-server/src/com/damon/ming/ai/rag/embedding/embedding_gateway.py
"""按角色路由 embedding 请求并应用 RAG 文本规则。"""

from src.com.damon.ming.ai.rag.embedding.BaseEmbeddingService import (
    BaseEmbeddingService,
)
from src.com.damon.ming.ai.rag.embedding.config.embedding_config_loader import (
    EmbeddingBusinessConfigLoader,
)


class EmbeddingGateway:
    """统一 embedding 入口，后端由启动配置装配。"""

    def __init__(self, roles: dict[str, dict]) -> None:
        """合并业务配置并按角色装配 embedding 引擎。"""
        from src.com.damon.ming.ai.rag.embedding.vllm_embedding import VllmEmbedding

        params = EmbeddingBusinessConfigLoader().load(roles)
        self._models = {role: VllmEmbedding(config) for role, config in params.items()}

    def _resolve(self, role: str) -> BaseEmbeddingService:
        try:
            return self._models[role]
        except KeyError as exc:
            raise ValueError(f"未配置 embedding role: {role}") from exc

    def get(self, role: str) -> "RoleEmbedding":
        self._resolve(role)
        return RoleEmbedding(self, role)

    def get_bge_m3(self) -> "RoleEmbedding":
        return self.get("bge_m3")

    def embed_query(self, role: str, text: str) -> list[float]:
        engine = self._resolve(role)
        return engine.embed_query(engine.params.query_prefix + text)

    def embed_documents(self, role: str, texts: list[str]) -> list[list[float]]:
        engine = self._resolve(role)
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), engine.params.batch_size):
            batch = texts[start : start + engine.params.batch_size]
            result = engine.embed_documents(
                [engine.params.passage_prefix + text for text in batch]
            )
            if len(result) != len(batch):
                raise ValueError("embedding 服务返回的向量数量与请求不一致")
            embeddings.extend(result)
        return embeddings


class RoleEmbedding(BaseEmbeddingService):
    """绑定角色的同步 embedding 接口。"""

    def __init__(self, gateway: EmbeddingGateway, role: str) -> None:
        super().__init__(gateway._resolve(role).params)
        self._gateway = gateway
        self._role = role

    @property
    def max_input_tokens(self) -> int | None:
        engine = self._gateway._resolve(self._role)
        limit = engine.max_input_tokens
        prefix = engine.params.passage_prefix
        if limit is None or not prefix:
            return limit
        tokenizer = engine.get_tokenizer()
        if tokenizer is None:
            raise ValueError("配置文档前缀时需要 tokenizer 计算输入上限")
        available = limit - len(tokenizer.encode(prefix, add_special_tokens=False)) - 8
        if available <= 0:
            raise ValueError("Embedding 模型输入上限不足以容纳文档前缀")
        return available

    def get_tokenizer(self):
        return self._gateway._resolve(self._role).get_tokenizer()

    def embed_query(self, text: str) -> list[float]:
        return self._gateway.embed_query(self._role, text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._gateway.embed_documents(self._role, texts)

    def get_model_info(self) -> dict:
        info = dict(self._gateway._resolve(self._role).get_model_info())
        info.update(
            query_prefix=self.params.query_prefix,
            passage_prefix=self.params.passage_prefix,
        )
        return info
