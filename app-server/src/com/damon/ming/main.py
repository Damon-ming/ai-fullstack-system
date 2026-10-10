# app-server/src/com/damon/ming/main.py

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.com.damon.ming.ai.inference.config import InferenceConfig
from src.com.damon.ming.ai.rag_tool import get_rag_container
from src.com.damon.ming.ai.registry.inference_registry import register_all_inferences
from src.com.damon.ming.debug import is_debug
from src.com.damon.ming.encryption.globals import (
    set_key_manager,
    set_signature_secret,
)
from src.com.damon.ming.encryption.key_management import KeyManager
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware import AuthMiddleware, EncryptionMiddleware
from src.com.damon.ming.router.account import account_router
from src.com.damon.ming.router.chat import chat_router
from src.com.damon.ming.router.encryption import encryption_router
from src.com.damon.ming.router.upload import upload_router
from src.com.damon.ming.router.upload.service.upload_service import UploadService

logger = pin("app.main")

# ---------------------------------------------------------------------------
# 环境判断（来自全局 debug 模块）
# ---------------------------------------------------------------------------

IS_DEBUG = is_debug()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("lifespan startup begin | debug=%s", IS_DEBUG)

    UploadService.init_sha_cache()

    # ========== 数据库连接池初始化 ==========
    # 优先级：DB_CONNECTION 环境变量 > YAML 配置文件 > 不启用
    _db_conn = None
    db_url = os.environ.get("DB_CONNECTION", "")
    if db_url:
        # 方式一：环境变量直接指定连接字符串
        try:
            from src.com.damon.ming.db import DbConfig, DbConnection, set_default_db

            _db_config = DbConfig(connection_string=db_url)
            _db_conn = DbConnection(_db_config)
            _db_conn.initialize(min_conn=1, max_conn=5)
            set_default_db(_db_conn)
            logger.info("数据库连接池初始化完成（环境变量 DB_CONNECTION）")
        except Exception as e:
            logger.warning("数据库连接池初始化失败: %s", e)
            _db_conn = None
    else:
        # 方式二：从 YAML 配置文件加载
        try:
            from src.com.damon.ming.db import DbConfigLoader, DbConnection, set_default_db

            _loader = DbConfigLoader()
            _db_config = _loader.load(profile="default" if IS_DEBUG else "production")
            _db_conn = DbConnection(_db_config)
            _pool = _loader.get_pool_settings(profile="default" if IS_DEBUG else "production")
            _db_conn.initialize(**_pool)
            set_default_db(_db_conn)
            logger.info("数据库连接池初始化完成（YAML 配置）")
        except FileNotFoundError:
            logger.info("数据库配置文件不存在，跳过数据库初始化")
        except Exception as e:
            logger.warning("数据库连接池初始化失败: %s", e)
            _db_conn = None

    # ========== 加密体系初始化 ==========
    logger.info("正在初始化加密体系...")
    _enc_config = None
    try:
        from src.com.damon.ming.encryption import EncryptionConfigLoader
        _enc_config = EncryptionConfigLoader().load(
            profile="default" if IS_DEBUG else "production"
        )
        logger.info(
            "加密配置加载完成 | rsa=%d | ttl=%dh",
            _enc_config.rsa_key_size,
            _enc_config.session_ttl_hours,
        )
    except FileNotFoundError:
        logger.info("加密配置文件不存在，使用默认参数")
    except Exception as e:
        logger.warning("加密配置加载失败，使用默认参数: %s", e)

    _key_store = None
    _kek = None
    if _db_conn is not None:
        try:
            from src.com.damon.ming.encryption.key_store import (
                PgKeyStore,
                derive_kek,
            )
            _key_store = PgKeyStore(_db_conn)
            _kek = derive_kek()
            logger.info("密钥持久化存储已启用（PostgreSQL）")
        except Exception as e:
            logger.warning("密钥持久化存储初始化失败，降级为纯内存: %s", e)
            _key_store = None
            _kek = None
    else:
        logger.info("密钥持久化存储未配置（纯内存模式，重启后会话丢失）")

    _rsa_size = _enc_config.rsa_key_size if _enc_config else 2048
    key_manager = KeyManager(rsa_key_size=_rsa_size, key_store=_key_store, kek=_kek)
    key_manager.initialize()
    set_key_manager(key_manager)
    logger.info("加密体系初始化完成 | rsa=%d", _rsa_size)

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
    if _db_conn is not None:
        _db_conn.close()
        logger.info("数据库连接池已关闭")


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

app.include_router(account_router.router)
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
