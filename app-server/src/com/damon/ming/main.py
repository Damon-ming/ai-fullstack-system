# app-server/src/com/damon/ming/main.py
"""
应用入口 —— FastAPI 装配 + 子系统挂载 + 全局中间件。

══════════════════════════════════════════════════════════════════════
环境变量清单
══════════════════════════════════════════════════════════════════════

【必须设置】
  MASTER_KEY              加密主密钥（≥32 字符，见 encryption/constants.py）
  INFERENCE_API_KEYS      各角色 api_key 映射 JSON（须覆盖 roles 段全部角色，缺失则启动报错）

【可选（本地开发用，生产镜像通过 build_info.py 固化）】
  APP_ENV                 环境标志：debug / release（默认 debug）
  LOG_LEVEL               日志级别：DEBUG / INFO / WARNING / ERROR（默认 INFO）
  INFERENCE_SERVER        推理后端：ollama / vllm / sglang（默认 ollama，连接信息由环境变量注入）
  INFERENCE_GATEWAY_URL   推理网关地址（默认 http://inference-gateway:8080/v1）
  INFERENCE_TIMEOUT       推理超时秒数（默认 180）
  INFERENCE_TEMPERATURE        聊天采样温度（环境变量覆盖 rag-runtime.yaml，格式 ROLE_PARAM）【未实现】
  CORS_ORIGINS            Release 模式的 CORS 允许来源（逗号分隔）

【配置文件（YAML）】
  app/config/db/db-config.yaml  数据库连接池配置（由 app 层注入 db 模块）
  app/config/encryption/encryption-config.yaml  加密业务配置（RSA 密钥大小、会话 TTL、sign_context 等，由 app 层注入 encryption 模块）

【环境变量读取入口】
  环境变量统一在 app/config/env.py 定义和读取，新增变量请加到该模块。
  各 loader 通过 getter 取值，负责与 YAML 合并及业务校验。

【构建时注入（生产环境）】
  src/com/damon/ming/debug/build_info.py  由 Dockerfile/CI 在镜像构建时生成
  SERVER_BUILD_ENV=0 → 锁定 release | =1 → 可切换（启动时冻结）
  → 存在此文件时 APP_ENV 环境变量被忽略，运行时不可变
  → 本地开发无需此文件，默认 debug
══════════════════════════════════════════════════════════════════════
"""

import sys

import uvicorn
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from src.com.damon.ming.app import AppInitializer, create_lifespan
from src.com.damon.ming.debug import is_debug
from src.com.damon.ming.exception import register_exception_handler
from src.com.damon.ming.log import init_logging, pin
from src.com.damon.ming.middleware import register_middlewares
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
# 日志初始化（环境感知：debug → stdout，release → 文件）
# ---------------------------------------------------------------------------

init_logging(is_debug=is_debug())

# ---------------------------------------------------------------------------
# 启动前校验 —— 缺少关键配置时立即终止，避免运行时才发现
# ---------------------------------------------------------------------------

_precheck_errors = run_precheck()
if _precheck_errors:
    logger.error("启动失败，请检查上述环境变量/配置")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 初始化器（封装所有子系统的启动/关闭）
# ---------------------------------------------------------------------------

initializer = AppInitializer()

# ---------------------------------------------------------------------------
# App 装配
# ---------------------------------------------------------------------------

app = FastAPI(
    title="我的多功能应用",
    lifespan=create_lifespan(initializer),
)


# ---- 速率限制（per-IP，slowapi）--------------------------------------
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# ---- 中间件注册 --------------------------------------------------------
# inbound:  CORS → Encryption → Auth → I18n → Context → 路由
# outbound: 路由 → Context → I18n → Auth → Encryption → CORS
# 详细逻辑见 middleware/__init__.py
register_middlewares(app)

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

# 容器内必须绑全接口：nginx 是独立容器，经 Docker 内网访问本服务，
# 绑 127.0.0.1 会让前端 /api/ 全部 502。
# 公网暴露由 compose 控制（app-server 用 expose，不发布端口），
# 因此这里绑 0.0.0.0 不会暴露到宿主机。
_HOST = "0.0.0.0"  # nosec B104 - 见上：容器网络命名空间内绑定，非公网暴露
_PORT = 8000

if __name__ == "__main__":
    logger.info(
        "启动 FastAPI 服务 | host=%s | port=%s | debug=%s", _HOST, _PORT, is_debug()
    )
    uvicorn.run(
        app,
        host=_HOST,
        port=_PORT,
        workers=1,  # GPU项目必须保持1个worker，不能多（多worker导致CUDA上下文重复加载，显存爆炸）
        limit_concurrency=50,  # 并发连接上限含SSE长连接；GPU推理能力(1-4并发)才是真正瓶颈，此值足够。
        # 若未来用户量增长优先扩GPU，盲目调大只会增加GPU排队延迟。
    )
