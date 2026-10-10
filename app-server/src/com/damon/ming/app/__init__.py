# app-server/src/com/damon/ming/app/__init__.py
"""
应用初始化模块 —— 统一管理所有子系统的启动和关闭。

提供：
  - AppInitializer: 封装数据库、加密、签名、RAG、LLM 的初始化逻辑
  - create_lifespan: 工厂函数，生成 FastAPI 可用的 lifespan 回调

用法（在 main.py 中）：
    from src.com.damon.ming.app import AppInitializer, create_lifespan

    initializer = AppInitializer(is_debug=IS_DEBUG)
    app = FastAPI(title="...", lifespan=create_lifespan(initializer), debug=IS_DEBUG)
"""

from src.com.damon.ming.app.app_initializer import AppInitializer, create_lifespan

__all__ = ["AppInitializer", "create_lifespan"]
