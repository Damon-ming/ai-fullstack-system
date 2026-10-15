# app-server/src/com/damon/ming/ai/rerank/factory.py

from src.com.damon.ming.ai.rerank.base_reranker import BaseReranker
from src.com.damon.ming.ai.rerank.cross_encoder_reranker import CrossEncoderReranker
from src.com.damon.ming.log import pin


class RerankerFactory:
    _registry: dict[str, type[BaseReranker]] = {}  # noqa: RUF012

    @classmethod
    def register(cls, name: str, impl_cls: type[BaseReranker]):
        if not issubclass(impl_cls, BaseReranker):
            raise TypeError("必须继承 BaseReranker")
        cls._registry[name] = impl_cls
        pin("RerankerFactory").info(f"注册reranker: {name}")

    @classmethod
    def create(cls, rerank_type: str, **kwargs) -> BaseReranker:
        if rerank_type not in cls._registry:
            raise ValueError(
                f"不支持rerank类型 {rerank_type}, 可用: {list(cls._registry.keys())}"
            )
        return cls._registry[rerank_type](**kwargs)


# 启动时注册
RerankerFactory.register("cross_encoder", CrossEncoderReranker)
