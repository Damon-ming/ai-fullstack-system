# app-server/src/com/damon/ming/app/app_initializer.py
"""
应用初始化器 —— 统一管理所有子系统的启动/关闭生命周期。

职责：
  - 数据库连接池（从 YAML 配置加载，失败则启动报错）
  - 加密体系（RSAKeyPair + KeyMaterial + SessionService）
  - 签名密钥
  - RAG 知识库
  - LLM 推理客户端
  - 上传服务 SHA 缓存
"""

import os
from contextlib import asynccontextmanager

from src.com.damon.ming.log import pin

logger = pin("app.init")


class AppInitializer:
    """应用初始化器。

    用法:
        init = AppInitializer(is_debug=True)
        init.startup()
        # ... 运行应用 ...
        init.shutdown()
    """

    def __init__(self, is_debug: bool = True) -> None:
        self._is_debug = is_debug
        self._profile = "common"  # 仅 common 剖面，无 production

        # 子系统状态（startup 后填充）
        self.system_config = None
        self.db_conn = None
        self.rsa_key_pair = None
        self.key_material = None
        self.session_service = None
        self.limiter = None
        self.pool_mgr = None
        self.rag_app = None
        self.infer_service = None
        self.guardrail = None
        self.inference: dict = {}
        self.llm_model_name: str = ""
        self.llm_options: dict = {}

        # 上传改为逐文件同步入库，无需后台任务

    # -----------------------------------------------------------------------
    # 生命周期
    # -----------------------------------------------------------------------

    def startup(self) -> None:
        """启动所有子系统。"""
        logger.info(
            "应用启动开始 | debug=%s | profile=%s", self._is_debug, self._profile
        )

        self._register_exception_types()
        self._init_system_config()  # 必须在其他子系统之前：提供 knowledge_dir
        self._init_thread_pool()
        self._init_upload_config()
        self._init_upload_service()
        self._init_i18n()
        self._init_database()
        self._init_encryption()
        self._init_sign_context()
        self._init_rate_limiter()
        self._init_chat()  # 必须在 _init_ai 之前：创建 infer_sem 供 RAGContainer 传递
        self._init_ai()
        self._init_guardrail()

        logger.info("应用启动完成")

    def attach_to_app(self, app) -> None:
        """将初始化完成的子系统挂载到 FastAPI app.state，供路由层使用。

        必须在 startup() 之后调用，确保所有子系统已初始化。
        """
        app.state.system_config = self.system_config
        app.state.rag_app = self.rag_app
        app.state.infer_service = self.infer_service
        app.state.guardrail = self.guardrail
        app.state.llm_model_name = self.llm_model_name
        app.state.llm_options = self.llm_options
        app.state.pool_mgr = self.pool_mgr

        # 聊天配置（Semaphore 在 lifespan 内创建，绑定到正确的事件循环）
        app.state.infer_sem = self.chat_sem
        app.state.rag_sem = self.rag_sem
        app.state.guardrail_sem = self.guardrail_sem
        app.state.infer_timeout = self.chat_timeout
        app.state.guardrail_timeout = self.guardrail_timeout
        app.state.retry_ms = self.chat_retry_ms
        app.state.chat_locales = self.chat_locales

        # 上传配置（文件类型白名单 + 大小上限 + 时间窗口）
        app.state.upload_config = self.upload_config

        # 数据库连接（上传审计表写入）
        app.state.db_conn = self.db_conn

        # 加密会话服务（RSA + 内存 + 可选 DB 持久化）
        app.state.session_service = self.session_service

        # 速率限制器（slowapi，per-IP 限流）
        app.state.limiter = self.limiter

        logger.info("子系统已挂载到 app.state")

    def shutdown(self) -> None:
        """关闭所有子系统，释放资源。"""
        logger.info("应用关闭，释放资源")

        # 1. 关闭线程池
        if self.pool_mgr is not None:
            self.pool_mgr.shutdown(wait=True, cancel_futures=True)
            logger.info("线程池管理器已关闭")

        # 3. 关闭数据库
        if self.db_conn is not None:
            self.db_conn.close()
            logger.info("数据库连接池已关闭")

    # -----------------------------------------------------------------------
    # 子系统初始化
    # -----------------------------------------------------------------------

    def _init_i18n(self) -> None:
        """i18n 模块初始化：加载配置 + 注入 LocalResolver。"""
        import os

        # 加载 YAML 配置
        from src.com.damon.ming.app.config.i18n.i18n_config_loader import (
            I18nConfigLoader,
        )
        from src.com.damon.ming.i18n import configure
        from src.com.damon.ming.i18n.locale_negotiator import (
            configure as configure_negotiator,
        )
        from src.com.damon.ming.i18n.resolver import LocalResolver

        i18n_cfg = I18nConfigLoader().load()
        configure_negotiator(
            default_locale=i18n_cfg.default_locale,
            supported_locales=i18n_cfg.supported_locales,
        )

        # 注入 resolver
        locales_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "i18n",
            "locales",
        )
        locales_dir = os.path.normpath(locales_dir)
        configure(
            LocalResolver(
                locales_dir=locales_dir,
                default_locale=i18n_cfg.default_locale,
                supported_locales=set(i18n_cfg.supported_locales),
            )
        )
        logger.info(
            "i18n 模块初始化完成 | default=%s | supported=%s | locales_dir=%s",
            i18n_cfg.default_locale,
            i18n_cfg.supported_locales,
            locales_dir,
        )

    def _init_thread_pool(self) -> None:
        """线程池管理器：从 YAML 加载配置，初始化所有线程池。

        线程池是核心依赖，配置加载失败直接抛出异常（不做静默降级）。
        """
        from src.com.damon.ming.app.config.thread import ThreadPoolConfigLoader
        from src.com.damon.ming.thread import ThreadPoolManager

        loader = ThreadPoolConfigLoader()
        pool_configs = loader.load()
        logger.info("线程池配置已从 YAML 加载: %s", pool_configs)

        self.pool_mgr = ThreadPoolManager()
        self.pool_mgr.startup(pool_configs=pool_configs)
        logger.info("线程池管理器初始化完成")

    def _init_upload_config(self) -> None:
        """上传配置：从 YAML 加载文件类型白名单 + 各自大小上限。

        上传配置是安全策略的一部分，加载失败直接抛出异常（不做静默降级）。
        """
        from src.com.damon.ming.app.config.upload import UploadConfigLoader

        loader = UploadConfigLoader()
        self.upload_config = loader.load()
        logger.info(
            "上传配置已加载 | allowed_types=%s",
            {
                k: f"{v['max_size_bytes'] // (1024 * 1024)}MB"
                for k, v in self.upload_config.allowed_types.items()
            },
        )

    def _init_system_config(self) -> None:
        """系统级配置：跨模块共享的路径和基础设置。

        必须在其他子系统之前初始化，后续模块从 self.system_config 获取路径。
        """
        from src.com.damon.ming.app.config.system import SystemConfigLoader

        loader = SystemConfigLoader()
        self.system_config = loader.load()
        logger.info(
            "系统配置已加载 | knowledge_dir=%s", self.system_config.knowledge_dir
        )

    def _register_exception_types(self) -> None:
        """注册子系统异常类型到全局异常分类器。"""
        try:
            from src.com.damon.ming.exception import (
                DatabaseError,
                EncryptionError,
                ServerSubSystem,
                register_exception,
            )

            register_exception(DatabaseError, ServerSubSystem.DATABASE)
            register_exception(EncryptionError, ServerSubSystem.ENCRYPTION)

            # 数据库驱动异常也归类为数据库子系统
            try:
                import sqlalchemy.exc

                register_exception(
                    sqlalchemy.exc.SQLAlchemyError, ServerSubSystem.DATABASE
                )
            except ImportError:
                pass

            logger.info("异常类型注册完成（Database / Encryption）")
        except Exception as e:
            logger.warning("异常类型注册失败: %s", e)

    def _init_upload_service(self) -> None:
        """上传服务：设置知识库目录 + 初始化 SHA 缓存（逐文件同步入库，无需后台任务）。"""
        from src.com.damon.ming.router.upload.service.upload_service import (
            UploadService,
        )

        UploadService.set_knowledge_dir(self.system_config.knowledge_dir)
        UploadService.init_sha_cache(sha_cache_max=self.upload_config.sha_cache_max)
        logger.info("上传服务初始化完成（逐文件同步入库模式）")

    def _init_database(self) -> None:
        """数据库连接池：仅从 YAML 配置文件加载。

        加载失败（文件不存在、格式错误、连接失败）直接抛出异常，
        不做静默降级——数据库是核心依赖，启动失败应明确报错。
        """
        from src.com.damon.ming.app.config.db.db_config_loader import DbConfigLoader
        from src.com.damon.ming.db import (
            DbConnection,
            set_default_db,
        )

        loader = DbConfigLoader()
        db_config = loader.load(profile=self._profile)
        self.db_conn = DbConnection(db_config)
        self.db_conn.initialize()  # pool 参数从 DbConfig 读取
        set_default_db(self.db_conn)
        self._create_account_tables()
        logger.info("数据库引擎初始化完成（YAML 配置）")

    def _create_account_tables(self) -> None:
        """创建账号体系表（users / devices / sessions）。"""
        try:
            from src.com.damon.ming.router.account.account_schema import (
                create_account_tables,
            )

            create_account_tables(self.db_conn)
            logger.info("账号体系表创建完成")
        except Exception as e:
            logger.warning("账号体系表创建失败: %s", e)

    def _init_rate_limiter(self) -> None:
        """速率限制器：slowapi 封装，per-IP 限流。"""
        from src.com.damon.ming.middleware.rate_limiter import limiter

        self.limiter = limiter
        logger.info("速率限制器初始化完成（per-IP，内存存储）")

    def _init_encryption(self) -> None:
        """加密体系：RSAKeyPair（纯技术）+ KeyMaterial（数据密钥）+ SessionService（业务协调）。"""
        from src.com.damon.ming.app.encryption.session_service import SessionService
        from src.com.damon.ming.encryption.globals import (
            set_key_material,
            set_rsa_key_pair,
        )
        from src.com.damon.ming.encryption.v1.key_management import KeyMaterial
        from src.com.damon.ming.encryption.v1.rsa_key_pair import RSAKeyPair

        self._enc_config = self._load_encryption_config()
        key_store, kek = self._create_key_store()
        rsa_size = self._enc_config.rsa_key_size if self._enc_config else 2048
        data_key_id = self._enc_config.data_key_id if self._enc_config else ""

        # 1. RSA 密钥对（纯技术）
        self.rsa_key_pair = RSAKeyPair(rsa_key_size=rsa_size)
        self.rsa_key_pair.initialize()
        set_rsa_key_pair(self.rsa_key_pair)

        # 2. 数据密钥材料（纯技术：字段加解密 + 盲索引）
        self.key_material = KeyMaterial(data_key_id=data_key_id)
        self.key_material.initialize()
        set_key_material(self.key_material)

        # 3. 会话服务（业务协调：RSA + 内存 + 可选 DB）
        ttl_seconds = (
            self._enc_config.session_ttl_seconds if self._enc_config else 60 * 60 * 24
        )
        self.session_service = SessionService(
            rsa_key_pair=self.rsa_key_pair,
            kek=kek or b"",
            ttl_seconds=ttl_seconds,
        )
        if key_store is not None:
            self.session_service.set_key_store(key_store)
        self.session_service.initialize()

        logger.info(
            "加密体系初始化完成 | rsa=%d | ttl=%dh | 持久化=%s",
            rsa_size,
            ttl_seconds // 3600,
            "启用" if key_store is not None else "纯内存",
        )

    def _load_encryption_config(self):
        """加载加密配置（可选，失败用默认值）。"""
        try:
            from src.com.damon.ming.app.config.encryption.encryption_config_loader import (
                EncryptionConfigLoader,
            )

            config = EncryptionConfigLoader().load(profile=self._profile)
            logger.info(
                "加密配置加载完成 | rsa=%d | ttl=%dh",
                config.rsa_key_size,
                config.session_ttl_hours,
            )
            return config
        except FileNotFoundError:
            logger.info("加密配置文件不存在，使用默认参数")
        except Exception as e:
            logger.warning("加密配置加载失败，使用默认参数: %s", e)
        return None

    def _create_key_store(self):
        """创建密钥存储后端（有数据库用 PgKeyStore，否则纯内存）。

        KEK 派生参数（salt / info）从业务配置注入，encryption 模块不包含这些常量。
        """
        if self.db_conn is None:
            logger.info("密钥持久化存储未配置（纯内存模式，重启后会话丢失）")
            return None, None

        try:
            from src.com.damon.ming.app.encryption.key_store import PgKeyStore
            from src.com.damon.ming.encryption.key_store import derive_kek

            if self._is_debug and not os.environ.get("MASTER_KEY"):
                from src.com.damon.ming.encryption.key_store.generate_master_key import (
                    inject_to_env,
                )

                key = inject_to_env()
                logger.warning("开发环境自动生成 MASTER_KEY（长度: %d）", len(key))

            # KEK 派生参数从业务配置读取（encryption 模块不包含这些协议常量）
            kek_salt = b""
            kek_info = b""
            if self._enc_config:
                kek_salt = (
                    self._enc_config.kek_salt.encode("utf-8")
                    if self._enc_config.kek_salt
                    else b""
                )
                kek_info = (
                    self._enc_config.kek_info.encode("utf-8")
                    if self._enc_config.kek_info
                    else b""
                )

            store = PgKeyStore(self.db_conn)
            store.initialize()
            kek = derive_kek(kek_salt=kek_salt, kek_info=kek_info)
            store.cleanup_expired()
            logger.info("密钥持久化存储已启用（PostgreSQL）")
            return store, kek
        except Exception as e:
            logger.warning("密钥持久化存储初始化失败，降级为纯内存: %s", e)
            return None, None

    def _init_sign_context(self) -> None:
        """HKDF 签名密钥派生 context：从 YAML 配置注入 encryption 模块。

        encryption 模块不包含此常量，由业务层配置提供。
        """
        from src.com.damon.ming.encryption.globals import set_sign_context

        if self._enc_config and self._enc_config.sign_context:
            set_sign_context(self._enc_config.sign_context.encode("utf-8"))
            logger.info("HKDF sign_context 已从配置注入")
        else:
            logger.warning("sign_context 未配置，签名密钥派生将使用空 context")

    def _init_chat(self) -> None:
        """聊天配置：加载 YAML 中的 Semaphore 参数、超时、多 locale 系统 prompt。"""
        import asyncio

        from src.com.damon.ming.app.config.inference.inference_runtime_config_loader import (
            ChatConfigLoader,
            ChatLocaleText,
        )

        configs = ChatConfigLoader().load_all()
        # 并发参数所有 locale 相同（来自 common），任选其一提取
        cfg = configs["zh_CN"]

        # Semaphore 在 lifespan 事件循环内创建，绑定到正确的 loop
        self.chat_sem = asyncio.Semaphore(cfg.infer_sem)
        self.rag_sem = asyncio.Semaphore(cfg.rag_sem)
        self.guardrail_sem = asyncio.Semaphore(cfg.guardrail_sem)
        self.chat_timeout = cfg.total_timeout
        self.guardrail_timeout = cfg.guardrail_timeout
        self.chat_retry_ms = cfg.sse_retry_ms
        # 多 locale 文本配置：locale → ChatLocaleText
        self.chat_locales = {
            locale: ChatLocaleText(
                system_prompt=c.system_prompt,
                ref_label=c.ref_label,
                query_label=c.query_label,
            )
            for locale, c in configs.items()
        }

        logger.info(
            "聊天配置初始化完成 | locales=%s | infer_sem=%d | rag_sem=%d | "
            "guardrail_sem=%d | guardrail_timeout=%ds | total_timeout=%ds",
            list(self.chat_locales.keys()),
            cfg.infer_sem,
            cfg.rag_sem,
            cfg.guardrail_sem,
            cfg.guardrail_timeout,
            cfg.total_timeout,
        )

    def _init_ai(self) -> None:
        """AI 子系统：推理注册 + RAG + LLM 客户端。"""
        from src.com.damon.ming.ai.rag_tool import get_rag_container
        from src.com.damon.ming.ai.registry.inference_registry import (
            register_all_inferences,
        )
        from src.com.damon.ming.app.config.inference.inference_runtime_config_loader import (
            InferenceConfigLoader,
        )

        register_all_inferences()
        # infer_sem 由 _init_chat() 创建（已在 lifespan 事件循环内），
        # 注入 RAGContainer → SummaryService，所有 LLM 调用共享同一信号量
        self.rag_app = get_rag_container(
            pool_mgr=self.pool_mgr,
            infer_sem=self.chat_sem,
            knowledge_dir=self.system_config.knowledge_dir,
        )

        # 全量加载推理引擎和模型（双源合并：环境变量连接 + inference-runtime.yaml 模型参数）
        _loader = InferenceConfigLoader()
        _loaded = _loader.load_all()
        self.inference = _loaded
        _chat_engine, _chat_entry = _loader.get_engine_for_model("chat")
        self.infer_service = _chat_engine
        self.llm_model_name = _chat_entry.model_name
        self.llm_options = _chat_entry.options
        logger.info(
            "RAG、LLM客户端初始化完成 | model=%s | engine=%s",
            self.llm_model_name,
            _chat_entry.engine_type,
        )

    def _init_guardrail(self) -> None:
        """护栏系统：加载配置，初始化护栏引擎（使用 guardrail 角色自己的引擎）。"""
        from src.com.damon.ming.ai.config.guardrail.guardrail_config_loader import (
            GuardrailConfigLoader,
        )

        loader = GuardrailConfigLoader()
        guardrail_engine, _ = self._loader.get_engine_for_model("guardrail")
        loaded = loader.load_all(inference=guardrail_engine)
        self.guardrail = loaded["engine"]
        logger.info("护栏系统初始化完成 | engine=%s", type(self.guardrail).__name__)


# ---------------------------------------------------------------------------
# 工厂函数：生成 FastAPI lifespan 回调
# ---------------------------------------------------------------------------


@asynccontextmanager
async def create_lifespan(initializer: AppInitializer):
    """生成 FastAPI 可用的 lifespan 回调。

    用法：
        initializer = AppInitializer(is_debug=IS_DEBUG)
        app = FastAPI(lifespan=create_lifespan(initializer))
    """
    initializer.startup()
    yield
    initializer.shutdown()
