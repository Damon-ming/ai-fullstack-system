# app-server/src/com/damon/ming/main.py
"""
应用入口 —— FastAPI 装配 + 子系统挂载 + 全局中间件。

══════════════════════════════════════════════════════════════════════
环境变量清单
══════════════════════════════════════════════════════════════════════

【必须设置】
  MASTER_KEY              加密主密钥（≥32 字符，见 encryption/constants.py）

【可选（本地开发用，生产镜像通过 build_info.py 固化）】
  APP_ENV                 环境标志：debug / release（默认 debug）
  LOG_LEVEL               日志级别：DEBUG / INFO / WARNING / ERROR（默认 INFO）
  INFERENCE_SERVER        推理后端：ollama / vllm / sglang（默认 ollama，连接信息由环境变量注入）
  INFERENCE_GATEWAY_URL   推理网关地址（默认 http://inference-gateway:8080/v1）
  INFERENCE_TIMEOUT       推理超时秒数（默认 180）
  INFERENCE_API_KEYS      各角色 api_key 映射 JSON（可选，默认见 inference_runtime_config_loader.py）
  CHAT_TEMPERATURE        聊天采样温度（环境变量覆盖 inference-runtime.yaml，格式 ROLE_PARAM）
  CORS_ORIGINS            Release 模式的 CORS 允许来源（逗号分隔）

【配置文件（YAML）】
  app/config/db/db-config.yaml  数据库连接池配置（由 app 层注入 db 模块）
  app/config/encryption/encryption-config.yaml  加密业务配置（RSA 密钥大小、会话 TTL、sign_context 等，由 app 层注入 encryption 模块）

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
from src.com.damon.ming.log import init_logging, pin
from src.com.damon.ming.middleware import AuthMiddleware, EncryptionMiddleware
from src.com.damon.ming.middleware.context_middleware import ContextMiddleware
from src.com.damon.ming.middleware.i18n_middleware import I18nMiddleware
from src.com.damon.ming.middleware.rate_limiter import rate_limit_handler
from src.com.damon.ming.precheck import run_precheck
from src.com.damon.ming.router.account import account_router
from src.com.damon.ming.router.chat import chat_router
from src.com.damon.ming.router.encryption import encryption_router
from src.com.damon.ming.router.history import history_router
from src.com.damon.ming.router.knowledge import knowledge_router
from src.com.damon.ming.router.upload import upload_router

logger = pin("app.main")


# ---------------------------------------------------------------------------
# 环境判断
# ---------------------------------------------------------------------------

IS_DEBUG = is_debug()

# ---------------------------------------------------------------------------
# 日志初始化（环境感知：debug → stdout，release → 文件）
# ---------------------------------------------------------------------------

init_logging(is_debug=IS_DEBUG)

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


# ---- 速率限制（per-IP，slowapi）--------------------------------------
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# ---- 中间件注册顺序说明 -----------------------------------------------
# Starlette 的 add_middleware 是 insert(0)：后添加的排最外层、最先执行。
# 因此本段按执行顺序倒序书写，实际执行顺序为：
#   CORS → Context → I18n → Auth → Encryption
# 新增中间件时按同一规则倒序添加。

# TODO: 上述四个中间件都继承 BaseHTTPMiddleware，而 BaseHTTPMiddleware 会经内存
#       stream 转发下游响应体；对 SSE / StreamingResponse 这类流式响应，历史上
#       多个 Starlette 版本存在响应体被缓冲、连接提前关闭、流式语义丢失等问题。
#       chat 走 SSE（SseEmitter），一旦出现流式响应异常，优先考虑改为纯 ASGI
#       中间件（直接实现 async def __call__(self, scope, receive, send)）。

# ---- 加密中间件 ---------------------------------------------------------
app.add_middleware(EncryptionMiddleware)

# ---- 认证中间件 ---------------------------------------------------------
if not IS_DEBUG:
    app.add_middleware(AuthMiddleware)
    logger.info("认证中间件已启用（release 模式）")
else:
    logger.info("认证中间件已禁用（debug 模式）")

# ---- i18n 语言协商 ------------------------------------------------------
app.add_middleware(I18nMiddleware)

# ---- 请求上下文（必须先于 i18n / auth / encryption 执行）--------------
# ContextMiddleware 一次性解析所有头部 → request.state.ctx / client / encryption
# 后续所有中间件和路由通过这三个键读取，不再直接访问 request.headers
# 必须在这三者之前注册：它是 i18n / auth / encryption 的数据来源
app.add_middleware(ContextMiddleware)

# ---- CORS（中间件链最外层）--------------------------------------------
# 必须最先执行：浏览器的 preflight（OPTIONS，按规范不带 Authorization）
# 要由 CORS 直接应答，否则会先被 AuthMiddleware 拦成 401，浏览器随即放弃
# 真实请求。同时 401 / 429 / 500 等响应也能带上 CORS 头，前端才读得到状态码。
#
# allow_headers 用 "*"：Starlette 只把单独的 "*" 当通配（"*" in allow_headers），
# 写成 "X-*" 会被当成字面量头部名，匹配不上任何真实头部。用 "*" 时 Starlette
# 会在 preflight 响应里回显客户端请求的头列表，因此带凭证（Authorization）也安全。
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
    release_origins = os.environ.get("CORS_ORIGINS", "").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in release_origins if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )
    logger.info("CORS: release 模式，允许来源: %s", release_origins)

# ---- 路由 --------------------------------------------------------------
app.include_router(account_router.router)
app.include_router(encryption_router.router)
app.include_router(upload_router.router)
app.include_router(history_router.router)
app.include_router(knowledge_router.router)
app.include_router(chat_router.router)
logger.info("应用路由初始化完成")

# ---- 全局异常处理器 ---------------------------------------------------
register_exception_handler(app)

# ── 存活探针（/ping /health 绕过所有中间件，供 Docker 探测）─────────
from src.com.damon.ming.middleware.health import wrap_health_app

app = wrap_health_app(app)

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("启动 FastAPI 服务 | host=127.0.0.1 | port=8000 | debug=%s", IS_DEBUG)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1,  # GPU项目必须保持1个worker，不能多（多worker导致CUDA上下文重复加载，显存爆炸）
        limit_concurrency=50,  # 并发连接上限含SSE长连接；GPU推理能力(1-4并发)才是真正瓶颈，此值足够。
        # 若未来用户量增长优先扩GPU，盲目调大只会增加GPU排队延迟。
    )
