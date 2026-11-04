# app-server/src/com/damon/ming/router/knowledge/__init__.py
"""
知识库目录 —— 对外暴露路由器和 Schema。

router 变量名与其它模块一致为 `router`，此处按 main.py 的引用口径
（`from ...router.knowledge import knowledge_router` 取子模块）不再重命名导出，
保证 `knowledge_router.router` 可访问。
"""

from src.com.damon.ming.router.knowledge.schemas.bean import KnowledgeNode

__all__ = ["KnowledgeNode", "knowledge_router"]
