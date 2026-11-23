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
from pathlib import Path

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
        # 子系统状态（startup 后填充）
        self.system_config = None
        self.db_conn = None
        self.rsa_key_pair = None
        self.key_material = None
        self.field_encryptor = None
        self.sign_context: bytes = b""
        self.session_service = None
        self.limiter = None
        self.pool_mgr = None
        self.rag_choreographer = None
        self.inference_gateway = None
        self.embedding_gateway = None

        # 上传改为逐文件同步入库，无需后台任务

    # -----------------------------------------------------------------------
    # 生命周期
    # -----------------------------------------------------------------------

    def startup(self) -> None:
        """启动所有子系统。"""
        from src.com.damon.ming.debug import is_debug

        logger.info("应用启动开始 | debug=%s", is_debug())

        self._register_exception_types()
        self._init_system_config()  # 必须在其他子系统之前：提供 corpus_dir
        self._init_thread_pool()
        self._init_upload_config()
        self._init_upload_service()
        self._init_i18n()
        self._init_database()
        self._init_encryption()
        self._init_sign_context()
        self._init_rate_limiter()
        self._init_ai()

        logger.info("应用启动完成")

    def attach_to_app(self, app) -> None:
        """将初始化完成的子系统挂载到 FastAPI app.state，供路由层使用。

        必须在 startup() 之后调用，确保所有子系统已初始化。
        按语义分组（定义见 app/app_state.py）；app.state.limiter 保持扁平，
        slowapi 框架硬编码读写该键。
        """
        from src.com.damon.ming.app.app_state import (
            AIRuntime,
            AppConfig,
            EncryptionState,
            InferenceRuntime,
            RagRuntime,
            Storage,
            ThreadRuntime,
        )

        app.state.config = AppConfig(
            system_config=self.system_config,
            upload_config=self.upload_config,
        )

        app.state.threads = ThreadRuntime(pool_mgr=self.pool_mgr)

        app.state.ai = AIRuntime(
            rag=RagRuntime(
                rag_sem=self.rag_sem,
                execution_timeout_seconds=self.execution_timeout_seconds,
                retry_ms=self.rag_retry_ms,
                model_root_dir=self.model_root_dir,
                locales=self.rag_locales,
                choreographer=self.rag_choreographer,
            ),
            inference=InferenceRuntime(
                gateway=self.inference_gateway,
            ),
        )

        app.state.storage = Storage(db_conn=self.db_conn)
        app.state.encryption = EncryptionState(
            session_service=self.session_service,
            field_encryptor=self.field_encryptor,
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

        # 2. 关闭 RAG 持有的向量存储
        if self.rag_choreographer is not None:
            self.rag_choreographer.close()

        # 3. 关闭应用数据库
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
        budget = loader.load()
        logger.info(
            "线程池全局预算已加载 | groups=%s | max_total=%d",
            budget.group_limits,
            budget.max_total_workers,
        )

        self.pool_mgr = ThreadPoolManager()
        self.pool_mgr.startup(
            group_limits=budget.group_limits,
            max_total_workers=budget.max_total_workers,
        )
        from src.com.damon.ming.app.thread_pools import create_io_pool

        create_io_pool()
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
        logger.info("系统配置已加载 | corpus_dir=%s", self.system_config.corpus_dir)

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
        """上传文件存储：设置知识库目录并清理遗留临时文件。"""
        from src.com.damon.ming.router.upload.service.upload_file_storage import (
            UploadFileStorage,
        )

        UploadFileStorage.set_corpus_dir(self.system_config.corpus_dir)
        UploadFileStorage.clean_temporary_files()
        logger.info("上传文件存储初始化完成")

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
            from src.com.damon.ming.app.tables import create_all_tables

            create_all_tables(self.db_conn)
            logger.info("业务表创建完成")
        except Exception as e:
            logger.exception("业务表创建失败，启动终止: %s", e)
            raise

    def _init_rate_limiter(self) -> None:
        """速率限制器: slowapi 封装, per-IP 限流。"""
        from src.com.damon.ming.middleware.rate_limiter import limiter

        self.limiter = limiter
        logger.info("速率限制器初始化完成(per-IP,内存存储)")

    def _init_encryption(self) -> None:
        """加密体系: RSAKeyPair(纯技术)+ KeyMaterial(数据密钥)+ SessionService(业务协调)。"""
        from src.com.damon.ming.app.encryption.field_encryption import (
            initialize_field_encryptor,
        )
        from src.com.damon.ming.app.encryption.field_key_material import KeyMaterial
        from src.com.damon.ming.app.encryption.field_key_store import PgFieldKeyStore
        from src.com.damon.ming.app.encryption.session_service import SessionService
        from src.com.damon.ming.app.thread_pools import create_database_pool
        from src.com.damon.ming.encryption.v1.rsa_key_pair import RSAKeyPair

        self._enc_config = self._load_encryption_config()
        key_store, kek = self._create_key_store()
        rsa_size = self._enc_config.rsa_key_size

        # 1. RSA 密钥对（纯技术）—— 注入 SessionService，不再另存全局副本
        self.rsa_key_pair = RSAKeyPair(key_size=rsa_size)
        self.rsa_key_pair.initialize()

        # 2. 字段加密密钥从数据库读取并缓存；首次启动时在 DB 创建密钥记录
        self.key_material = KeyMaterial(PgFieldKeyStore(self.db_conn))
        self.key_material.initialize()
        self.field_encryptor = initialize_field_encryptor(self.key_material)

        # 3. 会话服务（RSA + 必填 DB 存储，无会话密钥缓存）
        ttl_seconds = self._enc_config.session_ttl_seconds
        self.session_service = SessionService(
            rsa_key_pair=self.rsa_key_pair,
            kek=kek,
            ttl_seconds=ttl_seconds,
            key_store=key_store,
            db_executor=create_database_pool(),
        )
        self.session_service.initialize()

        logger.info(
            "加密体系初始化完成 | rsa=%d | ttl=%dh | 持久化=DB",
            rsa_size,
            ttl_seconds // 3600,
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
        """创建必填的数据库密钥存储后端，缺失或失败直接中止启动。

        KEK 派生参数(salt / info)从业务配置注入,encryption 模块不包含这些常量。
        """
        if self.db_conn is None:
            raise RuntimeError("加密会话必须使用数据库存储，请先初始化数据库连接")

        try:
            from src.com.damon.ming.app.encryption.key_store import PgKeyStore
            from src.com.damon.ming.encryption.key_store import derive_kek

            # KEK 派生参数从业务配置读取（encryption 模块不包含这些协议常量）
            kek_salt = self._enc_config.kek_salt.encode("utf-8")
            kek_info = self._enc_config.kek_info.encode("utf-8")

            store = PgKeyStore(self.db_conn)
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

    def _init_ai(self) -> None:
        """加载 AI 配置，初始化 RAG 容器和统一推理入口。"""
        import asyncio

        from src.com.damon.ming.ai.inference.inference_gateway import InferenceGateway
        from src.com.damon.ming.ai.rag.embedding import EmbeddingGateway
        from src.com.damon.ming.ai.rag.rag_tool import get_rag_choreographer
        from src.com.damon.ming.app.config.ai.embedding.embedding_config_loader import (
            EmbeddingConfigLoader,
        )
        from src.com.damon.ming.app.config.ai.inference.inference_config_loader import (
            InferenceConfigLoader,
        )
        from src.com.damon.ming.app.config.ai.rag.rag_runtime_config_loader import (
            RagConfigLoader,
        )
        from src.com.damon.ming.app.thread_pools import get_rag_pool_group
        from src.com.damon.ming.router.upload.service.upload_recovery_service import (
            UploadRecoveryService,
        )

        rag = RagConfigLoader().load().rag
        inference_config = InferenceConfigLoader().load()

        # Semaphore 在 lifespan 事件循环内创建，绑定到正确的 loop
        self.rag_sem = asyncio.Semaphore(rag.rag_max_concurrency)
        self.execution_timeout_seconds = rag.execution_timeout_seconds
        self.rag_retry_ms = rag.retry_ms
        self.model_root_dir = rag.model_root_dir
        # 多 locale 文本配置：locale → LocaleConfig
        self.rag_locales = rag.locales

        logger.info(
            "RAG 配置初始化完成 | locales=%s | rag_max_concurrency=%d | "
            "execution_timeout_seconds=%g",
            list(self.rag_locales.keys()),
            rag.rag_max_concurrency,
            rag.execution_timeout_seconds,
        )

        # 所有推理角色共享 Gateway 的并发限制。
        self.inference_gateway = InferenceGateway(
            inference_config.roles,
            asyncio.Semaphore(inference_config.max_concurrency),
        )

        self.embedding_gateway = EmbeddingGateway(
            EmbeddingConfigLoader().load(Path(self.model_root_dir))
        )

        self.rag_choreographer = get_rag_choreographer(
            pools=get_rag_pool_group(),
            corpus_dir=self.system_config.corpus_dir,
            model_root_dir=self.model_root_dir,
            inference_gateway=self.inference_gateway,
            embedding_gateway=self.embedding_gateway,
        )

        UploadRecoveryService.recover_startup(
            self.rag_choreographer.knowledge_index_service
        )

        logger.info("RAG 容器、推理 Gateway 与 Embedding Gateway 初始化完成")


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
