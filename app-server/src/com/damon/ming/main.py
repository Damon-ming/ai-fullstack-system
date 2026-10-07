# app-server/src/com/damon/ming/main.py

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.com.damon.ming.ai.inference.config import InferenceConfig
from src.com.damon.ming.ai.rag_tool import get_rag_container
from src.com.damon.ming.ai.registry.inference_registry import register_all_inferences
from src.com.damon.ming.encryption.globals import (
    set_key_manager,
    set_signature_secret,
)
from src.com.damon.ming.encryption.key_management import KeyManager
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware import AuthMiddleware, EncryptionMiddleware
from src.com.damon.ming.router.chat import chat_router
from src.com.damon.ming.router.encryption import encryption_router
from src.com.damon.ming.router.upload import upload_router
from src.com.damon.ming.router.upload.service.upload_service import UploadService

logger = pin("app.main")

# ---------------------------------------------------------------------------
# 环境判断
# ---------------------------------------------------------------------------

IS_DEBUG = os.environ.get("APP_ENV", "debug").lower() == "debug"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("lifespan startup begin | debug=%s", IS_DEBUG)

    UploadService.init_sha_cache()

    # ========== 加密体系初始化 ==========
    logger.info("正在生成 RSA 密钥对...")
    key_manager = KeyManager(rsa_key_size=2048)
    key_manager.initialize()
    set_key_manager(key_manager)
    logger.info("RSA-2048 密钥对生成完成")

    # 签名密钥（与环境变量保持一致，与前端共享）
    sig_secret = os.environ.get(
        "SIGNATURE_SECRET", "your-shared-secret-key-change-in-production"
    )
    set_signature_secret(sig_secret)
    logger.info("签名密钥已设置")

    register_all_inferences()
    rag_app = get_rag_container()

    infer_config = InferenceConfig()
    infer_profile = "default"
    infer_service = infer_config.create_infer_client(profile=infer_profile)
    llm_model_name = infer_config.get_llm_model_name(infer_profile)

    # 挂载到app.state，所有路由访问
    app.state.rag_app = rag_app
    app.state.infer_service = infer_service
    app.state.llm_model_name = llm_model_name

    logger.info("RAG、LLM客户端初始化完成")
    yield
    # ========== 应用关闭时 ==========
    logger.info("lifespan shutdown，释放资源")


# ---------------------------------------------------------------------------
# App 装配
# ---------------------------------------------------------------------------


app = FastAPI(title="我的多功能应用", lifespan=lifespan, debug=IS_DEBUG)

# ---- CORS ---------------------------------------------------------------
# debug: 允许所有来源（前端 dev server 端口任意）
# release: 限制为具体域名，allow_credentials 才能安全地设为 True
# 注意：allow_origins=["*"] 与 allow_credentials=True 冲突（浏览器安全策略），
#       release 环境必须指定具体 origins。

if IS_DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # debug 放行所有
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
        allow_headers=["Authorization", "Content-Type", "X-*"],  # 允许自定义头
    )
    logger.info("CORS: release 模式，允许来源: %s", release_origins)

# ---- 认证中间件 ---------------------------------------------------------
# debug: 不启用认证（开发方便）
# release: 启用，校验 device_auth_token
# 注意：认证中间件在 CORS 之后，这样 CORS 预检请求（OPTIONS）不需要认证

if not IS_DEBUG:
    app.add_middleware(AuthMiddleware)
    logger.info("认证中间件已启用（release 模式）")
else:
    logger.info("认证中间件已禁用（debug 模式）")

# ---- 加密中间件 ---------------------------------------------------------

app.add_middleware(EncryptionMiddleware)

# ---- 路由 --------------------------------------------------------------

app.include_router(encryption_router.router)
app.include_router(upload_router.router)
app.include_router(chat_router.router)
logger.info("应用路由初始化完成")


if __name__ == "__main__":
    logger.info("启动 FastAPI 服务 | host=0.0.0.0 | port=8000 | debug=%s", IS_DEBUG)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1,  # GPU项目必须保持1个worker，不能多
        limit_concurrency=50,  # 第一层防护：最多50个请求进入FastAPI，超过直接503
    )
