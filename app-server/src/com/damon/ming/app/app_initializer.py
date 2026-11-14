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

from contextlib import asynccontextmanager

from src.com.damon.ming.app.config.env import get_master_key
from src.com.damon.ming.log import pin

logger = pin("app.init")


class AppInitializer:
    """应用初始化器。

    用法:
        init = AppInitializer()
        init.startup()
        # ... 运行应用 ...
        init.shutdown()
    """

    def __init__(self) -> None:
        # 推理配置加载器：进程级单例（引擎只装配一次）
        from src.com.damon.ming.app.config.rag.rag_runtime_config_loader import (
            RagConfigLoader,
        )

        self._loader = RagConfigLoader()

        # 子系统状态（startup 后填充）
        self.system_config = None
        self.db_conn = None
        self.rsa_key_pair = None
        self.key_material = None
        self.sign_context: bytes = b""
        self.session_service = None
        self.limiter = None
        self.pool_mgr = None
        self.rag_app = None
        self.infer_service = None
        self.guardrail = None
        self.inference_model_name: str = ""
        self.inference_options: dict = {}

        # 上传改为逐文件同步入库，无需后台任务

    # -----------------------------------------------------------------------
    # 生命周期
    # -----------------------------------------------------------------------

    def startup(self) -> None:
        """启动所有子系统。"""
        from src.com.damon.ming.debug import is_debug

        logger.info("应用启动开始 | debug=%s", is_debug())

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
        self._init_rag()  # 必须在 _init_ai 之前：创建 infer_sem 供 RAGContainer 传递
        self._init_ai()
        self._init_guardrail()

        logger.info("应用启动完成")

    def attach_to_app(self, app) -> None:
        """将初始化完成的子系统挂载到 FastAPI app.state，供路由层使用。

        必须在 startup() 之后调用，确保所有子系统已初始化。
        按语义分组（定义见 app/app_state.py）；app.state.limiter 保持扁平，
        slowapi 框架硬编码读写该键。
        """
        from src.com.damon.ming.app.app_state import (
            AiServices,
            AppConfig,
            ChatRuntime,
            EncryptionState,
            GuardrailState,
            Storage,
        )

        app.state.config = AppConfig(
            system_config=self.system_config,
            upload_config=self.upload_config,
        )

        app.state.ai = AiServices(
            infer_service=self.infer_service,
            rag_app=self.rag_app,
            model_name=self.inference_model_name,
            options=self.inference_options,
            pool_mgr=self.pool_mgr,
        )

        app.state.guardrail = GuardrailState(
            engine=self.guardrail,
            sem=self.guardrail_sem,
            timeout_seconds=self.guardrail_timeout_seconds,
        )

        # Semaphore 在 lifespan 内创建，绑定到正确的事件循环
        app.state.chat = ChatRuntime(
            sem=self.chat_sem,
            retrieval_sem=self.retrieval_sem,
            execution_timeout_seconds=self.execution_timeout_seconds,
            retry_ms=self.chat_retry_ms,
            locales=self.chat_locales,
        )

        app.state.storage = Storage(db_conn=self.db_conn)

        app.state.encryption = EncryptionState(
            session_service=self.session_service,
            sign_context=self.sign_context,
        )

        # 速率限制器（slowapi，per-IP 限流）—— 保持扁平：框架硬性要求
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
        """i18n 模块初始化：加载 YAML 配置 + 交给 i18n 自己装配。"""
        from src.com.damon.ming.app.config.i18n.i18n_config_loader import (
            I18nConfigLoader,
        )
        from src.com.damon.ming.i18n import initialize as initialize_i18n

        i18n_cfg = I18nConfigLoader().load()
        initialize_i18n(
            default_locale=i18n_cfg.default_locale,
            supported_locales=i18n_cfg.supported_locales,
        )

    def _init_thread_pool(self) -> None:
        """线程池管理器：从 YAML 加载配置，初始化所有线程池。

        线程池是核心依赖，配置加载失败直接抛出异常（不做静默降级）。
        """
        from src.com.damon.ming.app.config.thread import ThreadPoolConfigLoader
        from src.com.damon.ming.thread import ThreadPoolManager

        loader = ThreadPoolConfigLoader()
        pool_configs = loader.load()
        rag_pools = self._loader.load().rag.thread_pools
        duplicates = pool_configs.keys() & rag_pools.keys()
        if duplicates:
            raise ValueError(
                f"通用与 RAG 线程池配置名称重复：{', '.join(sorted(duplicates))}"
            )
        pool_configs.update(rag_pools)
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

            logger.info("异常类型注册完成(Database / Encryption)")
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
        db_config = loader.load()
        self.db_conn = DbConnection(db_config)
        self.db_conn.initialize()  # pool 参数从 DbConfig 读取
        set_default_db(self.db_conn)
        self._create_tables()
        logger.info("数据库引擎初始化完成(YAML 配置)")

    def _create_tables(self) -> None:
        """创建全部业务表(account / encryption / history / upload)。"""
        try:
            from src.com.damon.ming.router.tables import create_all_tables

            create_all_tables(self.db_conn)
            logger.info("业务表创建完成")
        except Exception as e:
            logger.warning("业务表创建失败: %s", e)

    def _init_rate_limiter(self) -> None:
        """速率限制器: slowapi 封装, per-IP 限流。"""
        from src.com.damon.ming.middleware.rate_limiter import limiter

        self.limiter = limiter
        logger.info("速率限制器初始化完成(per-IP,内存存储)")

    def _init_encryption(self) -> None:
        """加密体系: RSAKeyPair(纯技术)+ KeyMaterial(数据密钥)+ SessionService(业务协调)。"""
        from src.com.damon.ming.app.encryption.session_service import SessionService
        from src.com.damon.ming.encryption.v1.key_management import KeyMaterial
        from src.com.damon.ming.encryption.v1.rsa_key_pair import RSAKeyPair

        self._enc_config = self._load_encryption_config()
        key_store, kek = self._create_key_store()
        rsa_size = self._enc_config.rsa_key_size
        data_key_id = self._enc_config.data_key_id

        # 1. RSA 密钥对（纯技术）—— 注入 SessionService，不再另存全局副本
        self.rsa_key_pair = RSAKeyPair(key_size=rsa_size)
        self.rsa_key_pair.initialize()

        # 2. 数据密钥材料（纯技术：字段加解密 + 盲索引）
        #    由使用方（FieldEncryptor）构造时注入，不再另存全局副本
        self.key_material = KeyMaterial(data_key_id=data_key_id)
        self.key_material.initialize()

        # 3. 会话服务（业务协调：RSA + 内存 + 可选 DB）
        ttl_seconds = self._enc_config.session_ttl_seconds
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
        """加载加密配置（必填，失败直接抛异常，不做静默降级）。"""
        from src.com.damon.ming.app.config.encryption.encryption_config_loader import (
            EncryptionConfigLoader,
        )
        from src.com.damon.ming.debug import get_env

        profile = get_env()
        config = EncryptionConfigLoader().load(profile=profile)
        logger.info(
            "加密配置加载完成 | profile=%s | rsa=%d | ttl=%dh",
            profile,
            config.rsa_key_size,
            config.session_ttl_hours,
        )
        return config

    def _create_key_store(self):
        """创建密钥存储后端(有数据库用 PgKeyStore,否则纯内存)。

        KEK 派生参数(salt / info)从业务配置注入,encryption 模块不包含这些常量。
        """
        if self.db_conn is None:
            logger.info("密钥持久化存储未配置(纯内存模式,重启后会话丢失)")
            return None, None

        try:
            from src.com.damon.ming.app.encryption.key_store import PgKeyStore
            from src.com.damon.ming.encryption.key_store import derive_kek

            # KEK 派生参数从业务配置读取（encryption 模块不包含这些协议常量）
            kek_salt = self._enc_config.kek_salt.encode("utf-8")
            kek_info = self._enc_config.kek_info.encode("utf-8")

            store = PgKeyStore(self.db_conn)
            store.initialize()
            # MASTER_KEY 由业务层读取并注入，encryption 模块不感知配置来源
            master_key = get_master_key()
            kek = derive_kek(
                kek_salt=kek_salt, kek_info=kek_info, master_key=master_key
            )
            store.cleanup_expired()
            logger.info("密钥持久化存储已启用(PostgreSQL)")
            return store, kek
        except Exception as e:
            # fail-closed：加密存储是安全关键路径，不允许降级为纯内存
            # （重启后所有加密会话丢失，且与「不允许静默降级」冲突）。
            # 不区分环境：debug 下开启加密时同样必须终止。
            logger.error("密钥持久化存储初始化失败，启动终止: %s", e)
            raise

    def _init_sign_context(self) -> None:
        """HKDF 签名密钥派生 context: 从 YAML 配置读出，挂到 app.state 供中间件取用。

        encryption 模块不包含此常量，由业务层配置提供。
        """
        self.sign_context = self._enc_config.sign_context.encode("utf-8")
        if not self.sign_context:
            raise RuntimeError(
                "sign_context 未配置，启动终止。"
                "签名密钥派生需要非空 context，请检查 encryption-config.yaml。"
            )
        logger.info("HKDF sign_context 已从配置读出")

    def _init_rag(self) -> None:
        """RAG 配置：从 YAML 读取 Semaphore 参数、超时、多 locale 文本。"""
        import asyncio

        cfg = self._loader.load()
        rag = cfg.rag

        # Semaphore 在 lifespan 事件循环内创建，绑定到正确的 loop
        self.chat_sem = asyncio.Semaphore(rag.shared_inference_max_concurrency)
        self.retrieval_sem = asyncio.Semaphore(rag.retrieval_max_concurrency)
        self.guardrail_sem = asyncio.Semaphore(rag.guardrail_max_concurrency)
        self.execution_timeout_seconds = rag.execution_timeout_seconds
        self.guardrail_timeout_seconds = rag.guardrail_timeout_seconds
        self.chat_retry_ms = rag.sse_retry_ms
        # 多 locale 文本配置：locale → LocaleConfig
        self.chat_locales = cfg.rag.locales

        logger.info(
            "RAG 配置初始化完成 | locales=%s | shared_inference_max_concurrency=%d | retrieval_max_concurrency=%d | "
            "guardrail_max_concurrency=%d | guardrail_timeout_seconds=%d | execution_timeout_seconds=%d",
            list(self.chat_locales.keys()),
            rag.shared_inference_max_concurrency,
            rag.retrieval_max_concurrency,
            rag.guardrail_max_concurrency,
            rag.guardrail_timeout_seconds,
            rag.execution_timeout_seconds,
        )

    def _init_ai(self) -> None:
        """AI 子系统：推理注册 + RAG + LLM 客户端。"""
        from src.com.damon.ming.ai.rag_tool import get_rag_container
        from src.com.damon.ming.ai.registry.inference_registry import (
            register_all_inferences,
        )

        register_all_inferences()
        # infer_sem 由 _init_rag() 创建（已在 lifespan 事件循环内），
        # 注入 RAGContainer → SummaryService，所有 LLM 调用共享同一信号量；
        # loader 同为注入，保证全进程只有一套推理引擎
        self.rag_app = get_rag_container(
            pool_mgr=self.pool_mgr,
            infer_sem=self.chat_sem,
            knowledge_dir=self.system_config.knowledge_dir,
            loader=self._loader,
        )

        # 推理引擎已由 self._loader.load() 装配（环境变量连接参数 + YAML roles 段）
        _inference_entry = self._loader.load().rag.roles["inference"]
        self.infer_service = _inference_entry.engine
        self.inference_model_name = _inference_entry.model_name
        self.inference_options = _inference_entry.options
        logger.info(
            "RAG、LLM客户端初始化完成 | model=%s | engine=%s",
            self.inference_model_name,
            _inference_entry.engine_type,
        )

    def _init_guardrail(self) -> None:
        """护栏系统：加载配置，初始化护栏引擎（使用 guardrail 角色自己的引擎）。"""
        from src.com.damon.ming.ai.config.guardrail.guardrail_config_loader import (
            GuardrailConfigLoader,
        )

        loader = GuardrailConfigLoader()
        guardrail_engine = self._loader.load().rag.roles["guardrail"].engine
        loaded = loader.load_all(inference=guardrail_engine)
        self.guardrail = loaded["engine"]
        logger.info("护栏系统初始化完成 | engine=%s", type(self.guardrail).__name__)


# ---------------------------------------------------------------------------
# 工厂函数：生成 FastAPI lifespan 回调
# ---------------------------------------------------------------------------


def create_lifespan(initializer: AppInitializer):
    """生成 FastAPI 可用的 lifespan 回调。

    用法：
        initializer = AppInitializer()
        app = FastAPI(lifespan=create_lifespan(initializer))

    注意：lifespan 参数要求传入**可调用对象**（(app) -> 异步上下文管理器），
    由框架在启动时调用。直接传 @asynccontextmanager 生成的上下文管理器实例
    会被框架二次调用，导致 "Application startup failed"。
    """

    @asynccontextmanager
    async def lifespan(app):
        initializer.startup()
        # startup 之后才挂载：app.state 必须拿到已初始化的子系统，
        # 在 import 期挂载会全部拿到 __init__ 里的默认值（None / 空）
        initializer.attach_to_app(app)
        yield
        initializer.shutdown()

    return lifespan
