# app-server/src/com/damon/ming/ai/intent/ollama_intention.py
import hashlib
import time
from typing import Any

from src.com.damon.ming.ai.intent.base_intention import BaseIntentionClassifier
from src.com.damon.ming.log import pin

logger = pin("OllamaIntentionClassifier")


class OllamaIntentionClassifier(BaseIntentionClassifier):
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

        # 意图识别固定Prompt模板（严格约束，只输出意图名称）
        self.intention_prompt_template = """
你是意图分类器，**只能输出一个意图名称，禁止额外文字、解释、标点**。
可选意图列表：{intention_list}
{extra_instruction}
用户问题：{query}
直接输出意图名称：
"""
        logger.info(f"意图识别模型初始化完成: {model_name}")

    def _get_cache_key(self, query: str, intention_list: list[str]) -> str:
        key_raw = f"{self.model_name}|{','.join(intention_list)}|{query}"
        return hashlib.md5(key_raw.encode("utf-8")).hexdigest()

    def classify(
        self,
        query: str,
        intention_list: list[str],
        extra_instruction: str | None = None,
    ) -> str:
        cache_key = self._get_cache_key(query, intention_list)
        if self.enable_cache and cache_key in self._cache:
            return self._cache[cache_key]

        extra_text = extra_instruction if extra_instruction else ""
        prompt = self.intention_prompt_template.format(
            intention_list=",".join(intention_list),
            extra_instruction=extra_text,
            query=query,
        )

        for attempt in range(self.max_retries):
            try:
                resp = self.client.generate(
                    model=self.model_name,
                    prompt=prompt,
                    options={"temperature": 0.0},  # 0温度，保证分类稳定不随机
                )
                pred_intention = resp["response"].strip()
                # 简单兜底：模型输出不在列表内，避免下游异常
                if pred_intention not in intention_list:
                    logger.warning(
                        f"模型输出意图不在允许列表，query={query}, output={pred_intention}"
                    )
                if self.enable_cache:
                    self._cache[cache_key] = pred_intention
                return pred_intention
            except Exception as e:
                wait = 2**attempt
                logger.warning(
                    f"意图识别请求失败，重试{attempt + 1}, wait {wait}s err:{e!s}"
                )
                time.sleep(wait)

        raise RuntimeError(f"意图识别调用失败，已达最大重试次数{self.max_retries}")

    def get_model_info(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "model": self.model_name,
            "base_url": self.base_url,
            "cache_enable": self.enable_cache,
            "cache_size": len(self._cache),
        }
