# app-server/src/com/damon/ming/ai/rewrite/ollama_rewriter.py
import hashlib
import time
from typing import Any

from src.com.damon.ming.ai.rewrite.base_rewriter import BaseQueryRewriter
from src.com.damon.ming.log import pin

logger = pin("OllamaQueryRewriter")


class OllamaQueryRewriter(BaseQueryRewriter):
    def __init__(
        self,
        model_name: str,
        base_url: str,
        timeout: int = 20,
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

        # 基础Prompt
        self.template_without_context = """
你是查询优化器，从用户原始描述提炼核心检索问题。
剔除情绪、铺垫、无关闲聊，保留实体、条件、疑问目标。
输出精简问句，不要解释、不要多余标点。
原始文本：
{query}
优化检索问句：
"""

        self.template_with_context = """
结合历史对话上下文，优化用户当前提问，补全指代、消除歧义。
只输出最终检索问句，禁止额外说明。
【历史上下文】
{context}
【用户当前问题】
{query}
优化检索问句：
"""

        logger.info(f"Query改写器初始化完成: {model_name}")

    def _get_cache_key(self, query: str, context: str | None) -> str:
        ctx = context or ""
        raw_key = f"{self.model_name}|{query}|{ctx}"
        return hashlib.md5(raw_key.encode("utf-8")).hexdigest()

    def rewrite(
        self, query: str, context: str | None = None, max_tokens: int = 256
    ) -> str:
        cache_key = self._get_cache_key(query, context)
        if self.enable_cache and cache_key in self._cache:
            return self._cache[cache_key]

        if context and context.strip():
            prompt = self.template_with_context.format(context=context, query=query)
        else:
            prompt = self.template_without_context.format(query=query)

        for attempt in range(self.max_retries):
            try:
                resp = self.client.generate(
                    model=self.model_name, prompt=prompt, options={"temperature": 0.1}
                )
                result = resp["response"].strip()
                if self.enable_cache:
                    self._cache[cache_key] = result
                return result
            except Exception as e:
                wait = 2**attempt
                logger.warning(
                    f"Query改写请求失败，重试{attempt + 1}, wait {wait}s err:{e!s}"
                )
                time.sleep(wait)

        raise RuntimeError(f"Query改写调用失败，已达最大重试次数{self.max_retries}")

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "model": self.model_name,
            "base_url": self.base_url,
            "cache_enable": self.enable_cache,
            "cache_size": len(self._cache),
        }
