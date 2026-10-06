# app-server/src/com/damon/ming/main.py

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.com.damon.ming.ai.inference.config import InferenceConfig
from src.com.damon.ming.ai.rag_tool import get_rag_container
from src.com.damon.ming.ai.registry.inference_registry import register_all_inferences
from src.com.damon.ming.chat.router import chat_router
from src.com.damon.ming.encryption.key_management import KeyManager
from src.com.damon.ming.encryption.middleware import EncryptionMiddleware, set_key_manager
from src.com.damon.ming.encryption.router import encryption_router
from src.com.damon.ming.log import pin
from src.com.damon.ming.upload.router import upload_router
from src.com.damon.ming.upload.service.upload_service import UploadService

logger = pin("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("lifespan startup begin")

    UploadService.init_sha_cache()
    
    # ========== 加密体系初始化 ==========
    logger.info("正在生成 RSA 密钥对...")
    key_manager = KeyManager(rsa_key_size=2048)
    key_manager.initialize()
    set_key_manager(key_manager)
    logger.info("RSA-2048 密钥对生成完成")

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
    # 在这里可以写关闭连接、释放资源的代码


app = FastAPI(title="我的多功能应用", lifespan=lifespan, debug=True)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源请求
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 加密中间件（必须在 CORS 之后、路由之前，才能拦截所有请求/响应）
app.add_middleware(EncryptionMiddleware)

# 密钥交换路由（本身不加密，必须在 EncryptionMiddleware 之后注册，
# 中间件会跳过对 /api/encryption/* 的处理）
app.include_router(encryption_router.router)

app.include_router(upload_router.router)
app.include_router(chat_router.router)
logger.info("应用路由初始化完成")

if __name__ == "__main__":
    logger.info("启动 FastAPI 服务 | host=0.0.0.0 | port=8000")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1,  # GPU项目必须保持1个worker，不能多
        limit_concurrency=50,  # 第一层防护：最多50个请求进入FastAPI，超过直接503
    )
