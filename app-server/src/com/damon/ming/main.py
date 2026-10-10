# app-server/src/com/damon/ming/main.py
"""
应用入口 —— FastAPI 装配 + 子系统挂载 + 全局中间件。

══════════════════════════════════════════════════════════════════════
环境变量清单
══════════════════════════════════════════════════════════════════════

【必须设置（否则启动失败）】
  SIGNATURE_SECRET        HMAC-SHA256 签名密钥（前后端共享，必须一致）

【生产环境必须设置（开发环境可自动生成）】
  MASTER_KEY              加密主密钥（≥32 字符），开发环境未设置时自动生成

【可选（有默认值或降级）】
  APP_ENV                 环境标志：debug / release（默认 debug）
  LOG_LEVEL               日志级别：DEBUG / INFO / WARNING / ERROR（默认 INFO）
  DB_CONNECTION           数据库连接串（未设置则跳过数据库初始化）
  DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD  DB 分项配置
  DB_CONFIG_PATH          DB YAML 配置文件路径（默认 db/db-config.yaml）
  ENCRYPTION_CONFIG_PATH  加密 YAML 配置文件路径（默认 encryption/encryption-config.yaml）
  CORS_ORIGINS            Release 模式的 CORS 允许来源（逗号分隔）

【配置文件（YAML）】
  db/db-config.yaml       数据库连接池配置（多剖面：default / production）
  encryption/encryption-config.yaml  加密参数配置（RSA 密钥大小、会话 TTL、KEK salt 等）
══════════════════════════════════════════════════════════════════════
"""

import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.com.damon.ming.app import AppInitializer, create_lifespan
from src.com.damon.ming.debug import is_debug
from src.com.damon.ming.exception import register_exception_handler
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware import AuthMiddleware, EncryptionMiddleware
from src.com.damon.ming.precheck import run_precheck
from src.com.damon.ming.router.account import account_router
from src.com.damon.ming.router.chat import chat_router
from src.com.damon.ming.router.encryption import encryption_router
from src.com.damon.ming.router.upload import upload_router

logger = pin("app.main")


# ---------------------------------------------------------------------------
# 环境判断
# ---------------------------------------------------------------------------

# 调试阶段：默认注入 debug 环境（上线前删除或注释此行）
os.environ.setdefault("APP_ENV", "DEBUG")

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
app.include_router(chat_router.router)
logger.info("应用路由初始化完成")

# ---- 挂载 AI 子系统到 app.state ----------------------------------------
app.state.rag_app = initializer.rag_app
app.state.infer_service = initializer.infer_service
app.state.llm_model_name = initializer.llm_model_name

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
