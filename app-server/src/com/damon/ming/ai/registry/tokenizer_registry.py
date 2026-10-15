# app-server/src/com/damon/ming/ai/registry/tokenizer_registry.py
from src.com.damon.ming.ai.tokenizer.tiktoken_tokenizer import TiktokenTokenizer
from src.com.damon.ming.ai.tokenizer.tokenizer_factory import TokenizerFactory
from src.com.damon.ming.log import pin

logger = pin("TokenizerRegistry")


def register_all_tokenizers():
    """启动时注册所有分词器实现"""
    TokenizerFactory.register("tiktoken", TiktokenTokenizer)
    logger.info(f"[Registry] 已注册分词器: {TokenizerFactory.list_providers()}")
