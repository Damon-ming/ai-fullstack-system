"""RAG 重排模型的初始化和访问入口。"""

from dataclasses import replace
from pathlib import Path

from src.com.damon.ming.ai.rag.rerank.base_reranker import BaseReranker
from src.com.damon.ming.ai.rag.rerank.config.rerank_config_loader import (
    RerankerConfigLoader,
)


class RerankersManager:
    def __init__(self) -> None:
        self._model_root_dir: Path | None = None
        self._config_loader: RerankerConfigLoader | None = None
        self._rerankers: dict[str, BaseReranker] = {}

    def initialize(self, model_root_dir: Path) -> None:
        if self._config_loader is not None:
            raise RuntimeError("RAG 重排器已经初始化")
        from src.com.damon.ming.ai.rag.rerank import list_engines
        from src.com.damon.ming.log import pin

        engines = list_engines()
        if engines:
            pin("RerankersManager").info("[Registry] 可用重排引擎: %s", engines)
        else:
            pin("RerankersManager").warning("[Registry] 未注册任何重排引擎")
        self._model_root_dir = model_root_dir
        self._config_loader = RerankerConfigLoader()

    def get(self, name: str) -> BaseReranker:
        """按 YAML 配置名获取重排器；每个模型只在首次获取时实例化一次。"""
        if self._config_loader is None or self._model_root_dir is None:
            raise RuntimeError("RAG 重排器尚未初始化")
        if name in self._rerankers:
            return self._rerankers[name]

        params = self._config_loader.load(name)
        model_path = Path(params.model_name)
        if not model_path.is_absolute():
            params = replace(
                params,
                model_name=str(self._model_root_dir / "rerank" / model_path),
            )

        # 当前项目的 reranker 配置使用 CrossEncoder 实现。
        from src.com.damon.ming.ai.rag.rerank import resolve_reranker

        reranker = resolve_reranker("cross_encoder")(params)
        self._rerankers[name] = reranker
        return reranker

    def get_bge_reranker_v2_m3(self) -> BaseReranker:
        """获取当前 RAG 主流程使用的 BGE-Reranker-v2-M3。"""
        return self.get("bge_reranker_v2_m3")
