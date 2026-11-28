# app-server/src/com/damon/ming/router/corpus/__init__.py
"""
知识库目录 —— 对外暴露路由器和 Schema。

router 变量名与其它模块一致为 `router`，此处按 main.py 的引用口径
（`from ...router.corpus import corpus_router` 取子模块）不再重命名导出，
保证 `corpus_router.router` 可访问。
"""

from src.com.damon.ming.router.corpus.schemas.bean import CorpusNode

__all__ = ["CorpusNode", "corpus_router"]
