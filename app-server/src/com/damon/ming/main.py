# app-server/src/com/damon/ming/main.py
"""
应用入口 —— FastAPI 装配 + 子系统挂载 + 全局中间件。

══════════════════════════════════════════════════════════════════════
环境变量清单
══════════════════════════════════════════════════════════════════════

【生产环境必须设置（开发环境可自动生成）】
  MASTER_KEY              加密主密钥（≥32 字符），开发环境未设置时自动生成

【可选（本地开发用，生产镜像通过 build_info.py 固化）】
  APP_ENV                 环境标志：debug / release（默认 debug）
  LOG_LEVEL               日志级别：DEBUG / INFO / WARNING / ERROR（默认 INFO）
  DB_CONFIG_PATH          DB YAML 配置文件路径（默认 app/config/db-config.yaml，可选）
  ENCRYPTION_CONFIG_PATH  加密 YAML 配置文件路径（默认 encryption/encryption-config.yaml）
  CORS_ORIGINS            Release 模式的 CORS 允许来源（逗号分隔）

【配置文件（YAML）】
  app/config/db-config.yaml  数据库连接池配置（多剖面：default / production，由 app 层注入 db 模块）
  app/config/encryption-config.yaml  加密业务配置（RSA 密钥大小、会话 TTL、sign_context 等，由 app 层注入 encryption 模块）

【构建时注入（生产环境）】
  src/com/damon/ming/debug/build_info.py  由 Dockerfile/CI 在镜像构建时生成
  SERVER_BUILD_ENV=0 → 锁定 release | =1 → 可切换（启动时冻结）
  → 存在此文件时 APP_ENV 环境变量被忽略，运行时不可变
  → 本地开发无需此文件，默认 debug
══════════════════════════════════════════════════════════════════════
"""

import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from src.com.damon.ming.app import AppInitializer, create_lifespan
from src.com.damon.ming.debug import is_debug
from src.com.damon.ming.exception import register_exception_handler
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware import AuthMiddleware, EncryptionMiddleware
from src.com.damon.ming.middleware.context_middleware import ContextMiddleware
from src.com.damon.ming.middleware.i18n_middleware import I18nMiddleware
from src.com.damon.ming.middleware.rate_limiter import rate_limit_handler
from src.com.damon.ming.precheck import run_precheck
from src.com.damon.ming.router.account import account_router
from src.com.damon.ming.router.chat import chat_router
from src.com.damon.ming.router.encryption import encryption_router
from src.com.damon.ming.router.history import history_router
from src.com.damon.ming.router.upload import upload_router

logger = pin("app.main")


# ---------------------------------------------------------------------------
# 环境判断
# ---------------------------------------------------------------------------

IS_DEBUG = is_debug()

# ---------------------------------------------------------------------------
# 启动前校验 —— 缺少关键配置时立即终止，避免运行时才发现
# ---------------------------------------------------------------------------

_precheck_errors = run_precheck(is_debug=IS_DEBUG)
if _precheck_errors:
    if IS_DEBUG:
        logger.warning("开发环境跳过校验缺失，启动继续")
    else:
        logger.error("启动失败，请检查上述环境变量/配置")
        sys.exit(1)

# ---------------------------------------------------------------------------
# 初始化器（封装所有子系统的启动/关闭）
# ---------------------------------------------------------------------------

initializer = AppInitializer(is_debug=IS_DEBUG)

# ---------------------------------------------------------------------------
# App 装配
# ---------------------------------------------------------------------------

app = FastAPI(
    title="我的多功能应用",
    lifespan=create_lifespan(initializer),
    debug=IS_DEBUG,
)

# ---- CORS ---------------------------------------------------------------
if IS_DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS: debug 模式，放行所有来源")
else:
    release_origins = os.environ.get(
        "CORS_ORIGINS", "https://your-production-domain.com"
    ).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in release_origins if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-*"],
    )
    logger.info("CORS: release 模式，允许来源: %s", release_origins)

# ---- 速率限制（per-IP，slowapi）--------------------------------------
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# ---- 请求上下文（必须在 auth / encryption 之前执行，因此先添加）------
# ContextMiddleware 一次性解析所有头部 → request.state.ctx
# 后续所有中间件和路由通过 ctx 读取，不再直接访问 request.headers
app.add_middleware(ContextMiddleware)

# ---- i18n 语言协商（必须在 auth / encryption 之前）--------------
app.add_middleware(I18nMiddleware)

# ---- 认证中间件 ---------------------------------------------------------
if not IS_DEBUG:
    app.add_middleware(AuthMiddleware)
    logger.info("认证中间件已启用（release 模式）")
else:
    logger.info("认证中间件已禁用（debug 模式）")

# ---- 加密中间件 ---------------------------------------------------------
app.add_middleware(EncryptionMiddleware)

# ---- 路由 --------------------------------------------------------------
app.include_router(account_router.router)
app.include_router(encryption_router.router)
app.include_router(upload_router.router)
app.include_router(history_router.router)
app.include_router(chat_router.router)
logger.info("应用路由初始化完成")

# ---- 初始化器将所有子系统挂载到 app.state --------------------------
initializer.attach_to_app(app)

# ---- 全局异常处理器 ---------------------------------------------------
register_exception_handler(app)

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("启动 FastAPI 服务 | host=0.0.0.0 | port=8000 | debug=%s", IS_DEBUG)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1,  # GPU项目必须保持1个worker，不能多
        limit_concurrency=50,
    )
