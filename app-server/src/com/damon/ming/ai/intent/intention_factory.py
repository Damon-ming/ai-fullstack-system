# app-server/src/com/damon/ming/ai/intent/intention_factory.py

from src.com.damon.ming.ai.intent.base_intention import BaseIntentionClassifier
from src.com.damon.ming.ai.intent.ollama_intention import OllamaIntentionClassifier
from src.com.damon.ming.log import pin

logger = pin("IntentionFactory")


class IntentionFactory:
    _registry: dict[str, type[BaseIntentionClassifier]] = {}

    @classmethod
    def register(cls, name: str, impl_cls: type[BaseIntentionClassifier]):
        if not issubclass(impl_cls, BaseIntentionClassifier):
            raise TypeError("意图分类器必须继承BaseIntentionClassifier")
        cls._registry[name] = impl_cls
        logger.info(f"注册意图识别模型: {name}")

    @classmethod
    def create(cls, provider: str, **kwargs) -> BaseIntentionClassifier:
        if provider not in cls._registry:
            raise ValueError(
                f"不支持的意图识别模型，可用列表：{list(cls._registry.keys())}"
            )
        return cls._registry[provider](**kwargs)

    @classmethod
    def list_providers(cls) -> list:
        return list(cls._registry.keys())


# 注册ollama实现
IntentionFactory.register("ollama", OllamaIntentionClassifier)
