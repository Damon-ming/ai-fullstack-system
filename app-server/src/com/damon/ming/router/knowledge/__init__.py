# app-server/src/com/damon/ming/router/knowledge/__init__.py
"""
知识库目录 —— 对外暴露路由器和 Schema。
"""

from src.com.damon.ming.router.knowledge.knowledge_router import knowledge_router
from src.com.damon.ming.router.knowledge.schemas.bean import KnowledgeNode

__all__ = ["KnowledgeNode", "knowledge_router"]
