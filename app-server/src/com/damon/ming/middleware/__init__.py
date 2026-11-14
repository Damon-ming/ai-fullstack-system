# app-server/src/com/damon/ming/middleware/__init__.py
"""
Middleware 模块入口。

用法：
    from src.com.damon.ming.middleware import register_middlewares
    register_middlewares(app)

约定：每个 middleware 自带 inbound + outbound 两段逻辑；
本模块按执行顺序倒序注册（见下方函数注释）。
"""

from fastapi import FastAPI
from src.com.damon.ming.debug import is_debug
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.auth_middleware import AuthMiddleware
from src.com.damon.ming.middleware.context_middleware import ContextMiddleware
from src.com.damon.ming.middleware.encryption_middleware import EncryptionMiddleware
from src.com.damon.ming.middleware.i18n_middleware import I18nMiddleware

logger = pin("middleware.init")

# 导出
__all__ = [
    "AuthMiddleware",
    "ContextMiddleware",
    "EncryptionMiddleware",
    "I18nMiddleware",
    "register_middlewares",
]


def register_middlewares(app: FastAPI) -> None:
    """注册所有中间件。

    每个 middleware 自带 inbound + outbound 两段逻辑，注册顺序决定执行顺序。
    Starlette 的 add_middleware 是 insert(0)：后注册的在外层（先执行 inbound）。

    本函数按「执行顺序倒序」注册，实际执行顺序为：
      inbound:  CORS → Encryption → Auth → I18n → Context → 路由
      outbound: 路由 → Context → I18n → Auth → Encryption → CORS
    """
    # ---- 按执行顺序倒序注册 ----------------------------------------
    # 1. 请求上下文（最内层）
    app.add_middleware(ContextMiddleware)

    # 2. i18n 语言协商
    app.add_middleware(I18nMiddleware)

    # 3. 认证中间件（所有环境启用）
    app.add_middleware(AuthMiddleware)
    logger.info("认证中间件已启用")

    # 4. 加密中间件（inbound 解密 + outbound 加密）
    app.add_middleware(EncryptionMiddleware)
    logger.info("加密中间件已启用")

    # 5. CORS（最外层，最先处理 preflight，最后处理响应头）
    from fastapi.middleware.cors import CORSMiddleware
    from src.com.damon.ming.app.config.env import get_cors_origins

    if is_debug():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info("CORS: debug 模式，放行所有来源")
    else:
        release_origins = get_cors_origins()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=release_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
            allow_headers=["*"],
        )
        logger.info("CORS: release 模式，允许来源: %s", release_origins)

    logger.info("中间件注册完成")
