# app-server/src/com/damon/ming/ai/summary/tiny_llm_summarizer.py
import hashlib
import time

from src.com.damon.ming.ai.summary.base_summarizer import BaseSummarizer
from src.com.damon.ming.log import pin

logger = pin("TinyLLMSummarizer")


class TinyLLMSummarizer(BaseSummarizer):
    def __init__(
        self,
        model_name: str,
        base_url: str,
        timeout: int,
        max_retries: int = 2,
        enable_cache: bool = True,
    ):
        try:
            import ollama
        except ImportError:
            raise ImportError("请安装依赖：pip install ollama")

        self.model_name = model_name
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = ollama.Client(host=base_url, timeout=timeout)
        self.enable_cache = enable_cache
        self._cache: dict[str, str] = {}

        # 固定摘要Prompt，轻量化
        self.summary_prompt_template = """
你是文本摘要助手，精简下面文档内容，保留全部关键数据、结论、条款，不要冗余描述。
摘要控制在{max_tokens}token以内，直接输出摘要，不要多余解释：
文档内容：
{content}
        """

        logger.info(f"轻量摘要模型初始化完成: {model_name}")

    def _get_cache_key(self, text: str, max_tokens: int) -> str:
        raw = f"{self.model_name}|{max_tokens}|{text}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def summarize(self, text: str, max_summary_tokens: int = 800) -> str:
        # 缓存命中直接返回
        cache_key = self._get_cache_key(text, max_summary_tokens)
        if self.enable_cache and cache_key in self._cache:
            return self._cache[cache_key]

        prompt = self.summary_prompt_template.format(
            max_tokens=max_summary_tokens, content=text
        )

        # 重试机制
        for attempt in range(self.max_retries):
            try:
                resp = self.client.generate(
                    model=self.model_name,
                    prompt=prompt,
                    options={"temperature": 0.1},  # 低温度保证摘要客观稳定
                )
                summary = resp["response"].strip()
                if self.enable_cache:
                    self._cache[cache_key] = summary
                return summary
            except Exception as e:
                wait = 2**attempt
                logger.warning(
                    f"摘要模型请求失败，重试{attempt + 1}, wait {wait}s err:{e!s}"
                )
                time.sleep(wait)

        raise RuntimeError(f"摘要生成失败，已达最大重试次数{self.max_retries}")

    def get_model_info(self) -> dict:
        return {
            "provider": "ollama_tiny_llm",
            "model": self.model_name,
            "base_url": self.base_url,
            "cache_enable": self.enable_cache,
            "cache_size": len(self._cache),
        }
