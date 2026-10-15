# app-server/src/com/damon/ming/ai/tokenizer/tokenizer_factory.py

from src.com.damon.ming.ai.tokenizer.base_tokenizer import BaseTokenizer
from src.com.damon.ming.ai.tokenizer.tiktoken_tokenizer import TiktokenTokenizer
from src.com.damon.ming.log import pin

logger = pin("TokenizerFactory")


class TokenizerFactory:
    _providers: dict[str, type[BaseTokenizer]] = {}

    @classmethod
    def register(cls, provider_name: str, tokenizer_cls: type[BaseTokenizer]):
        if not issubclass(tokenizer_cls, BaseTokenizer):
            raise TypeError(f"{tokenizer_cls} 必须继承 BaseTokenizer")
        cls._providers[provider_name] = tokenizer_cls
        logger.info(f"[TokenizerFactory] 注册分词器provider: {provider_name}")

    @classmethod
    def create(cls, provider: str, **kwargs) -> BaseTokenizer:
        if provider not in cls._providers:
            available = list(cls._providers.keys())
            raise ValueError(
                f"不支持的分词器provider: {provider}. 可用列表: {available}"
            )
        return cls._providers[provider](**kwargs)

    @classmethod
    def list_providers(cls) -> list:
        return list(cls._providers.keys())


# 内置注册tiktoken
TokenizerFactory.register("tiktoken", TiktokenTokenizer)
