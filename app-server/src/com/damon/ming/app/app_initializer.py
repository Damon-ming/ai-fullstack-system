# app-server/src/com/damon/ming/app/app_initializer.py
"""
应用初始化器 —— 统一管理所有子系统的启动/关闭生命周期。

职责：
  - 数据库连接池（可选，未配置则跳过）
  - 加密体系（KeyManager + 可选 PgKeyStore）
  - 签名密钥
  - RAG 知识库
  - LLM 推理客户端
  - 上传服务 SHA 缓存

每个子系统独立初始化，失败不影响其他子系统（降级处理）。
"""

import os
from contextlib import asynccontextmanager

from src.com.damon.ming.log import pin

logger = pin("app.init")


class AppInitializer:
    """应用初始化器。

    用法：
        init = AppInitializer(is_debug=True)
        init.startup()
        # ... 运行应用 ...
        init.shutdown()
    """

    def __init__(self, is_debug: bool = True) -> None:
        self._is_debug = is_debug
        self._profile = "default" if is_debug else "production"

        # 子系统状态（startup 后填充）
        self.db_conn = None
        self.key_manager = None
        self.rag_app = None
        self.infer_service = None
        self.llm_model_name: str = ""

    # -----------------------------------------------------------------------
    # 生命周期
    # -----------------------------------------------------------------------

    def startup(self) -> None:
        """启动所有子系统。"""
        logger.info(
            "应用启动开始 | debug=%s | profile=%s", self._is_debug, self._profile
        )

        self._register_exception_types()
        self._init_upload_service()
        self._init_database()
        self._init_encryption()
        self._init_signature()
        self._init_ai()

        logger.info("应用启动完成")

    def shutdown(self) -> None:
        """关闭所有子系统，释放资源。"""
        logger.info("应用关闭，释放资源")
        if self.db_conn is not None:
            self.db_conn.close()
            logger.info("数据库连接池已关闭")

    # -----------------------------------------------------------------------
    # 子系统初始化
    # -----------------------------------------------------------------------

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

            # psycopg2 数据库驱动异常也归类为数据库子系统
            try:
                import psycopg2

                register_exception(psycopg2.Error, ServerSubSystem.DATABASE)
            except ImportError:
                pass

            logger.info("异常类型注册完成（Database / Encryption）")
        except Exception as e:
            logger.warning("异常类型注册失败: %s", e)

    def _init_upload_service(self) -> None:
        """上传服务：初始化 SHA 缓存。"""
        from src.com.damon.ming.router.upload.service.upload_service import (
            UploadService,
        )

        UploadService.init_sha_cache()

    def _init_database(self) -> None:
        """数据库连接池：环境变量 > YAML 配置 > 跳过。"""
        db_url = os.environ.get("DB_CONNECTION", "")
        if db_url:
            self._init_database_from_url(db_url)
        else:
            self._init_database_from_yaml()

    def _init_database_from_url(self, db_url: str) -> None:
        """从环境变量 DB_CONNECTION 初始化数据库。"""
        try:
            from src.com.damon.ming.db import DbConfig, DbConnection, set_default_db

            self.db_conn = DbConnection(DbConfig(connection_string=db_url))
            self.db_conn.initialize(min_conn=1, max_conn=5)
            set_default_db(self.db_conn)
            logger.info("数据库连接池初始化完成（环境变量 DB_CONNECTION）")
        except Exception as e:
            logger.warning("数据库连接池初始化失败: %s", e)
            self.db_conn = None

    def _init_database_from_yaml(self) -> None:
        """从 YAML 配置文件初始化数据库。"""
        try:
            from src.com.damon.ming.db import (
                DbConfigLoader,
                DbConnection,
                set_default_db,
            )

            loader = DbConfigLoader()
            db_config = loader.load(profile=self._profile)
            self.db_conn = DbConnection(db_config)
            pool = loader.get_pool_settings(profile=self._profile)
            self.db_conn.initialize(**pool)
            set_default_db(self.db_conn)
            logger.info("数据库连接池初始化完成（YAML 配置）")
        except FileNotFoundError:
            logger.info("数据库配置文件不存在，跳过数据库初始化")
        except Exception as e:
            logger.warning("数据库连接池初始化失败: %s", e)
            self.db_conn = None

    def _init_encryption(self) -> None:
        """加密体系：配置加载 > KeyManager > 可选 PgKeyStore。"""
        self._enc_config = self._load_encryption_config()
        key_store, kek = self._create_key_store()
        rsa_size = self._enc_config.rsa_key_size if self._enc_config else 2048
        ttl_seconds = (
            self._enc_config.session_ttl_seconds if self._enc_config else 60 * 60 * 24
        )

        from src.com.damon.ming.encryption.globals import set_key_manager
        from src.com.damon.ming.encryption.key_management import KeyManager

        self.key_manager = KeyManager(
            rsa_key_size=rsa_size,
            key_store=key_store,
            kek=kek,
            session_ttl_seconds=ttl_seconds,
        )
        self.key_manager.initialize()
        set_key_manager(self.key_manager)
        logger.info(
            "加密体系初始化完成 | rsa=%d | ttl=%dh", rsa_size, ttl_seconds // 3600
        )

    def _load_encryption_config(self):
        """加载加密配置（可选，失败用默认值）。"""
        try:
            from src.com.damon.ming.encryption import EncryptionConfigLoader

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
        """创建密钥存储后端（有数据库用 PgKeyStore，否则纯内存）。"""
        if self.db_conn is None:
            logger.info("密钥持久化存储未配置（纯内存模式，重启后会话丢失）")
            return None, None

        try:
            from src.com.damon.ming.encryption.key_store import derive_kek
            from src.com.damon.ming.router.encryption.pg_key_store import PgKeyStore

            if self._is_debug and not os.environ.get("MASTER_KEY"):
                from src.com.damon.ming.encryption.key_store.generate_master_key import (
                    inject_to_env,
                )

                key = inject_to_env()
                logger.warning("开发环境自动生成 MASTER_KEY（长度: %d）", len(key))

            store = PgKeyStore(self.db_conn)
            kek = derive_kek()
            logger.info("密钥持久化存储已启用（PostgreSQL）")
            return store, kek
        except Exception as e:
            logger.warning("密钥持久化存储初始化失败，降级为纯内存: %s", e)
            return None, None

    def _init_signature(self) -> None:
        """签名密钥：环境变量 > YAML 配置，与前端共享。"""
        from src.com.damon.ming.encryption.globals import set_signature_secret
        from src.com.damon.ming.log.logger import security_warn

        # 优先级：环境变量 > YAML 配置
        sig_secret = os.environ.get("SIGNATURE_SECRET", "")
        if not sig_secret and self._enc_config:
            sig_secret = self._enc_config.signature_secret

        if not sig_secret:
            security_warn("SIGNATURE_SECRET 未设置，使用不安全的默认值")
            sig_secret = "your-shared-secret-key-change-in-production"

        set_signature_secret(sig_secret)
        logger.info("签名密钥已设置")

    def _init_ai(self) -> None:
        """AI 子系统：推理注册 + RAG + LLM 客户端。"""
        from src.com.damon.ming.ai.inference.config import InferenceConfig
        from src.com.damon.ming.ai.rag_tool import get_rag_container
        from src.com.damon.ming.ai.registry.inference_registry import (
            register_all_inferences,
        )

        register_all_inferences()
        self.rag_app = get_rag_container()

        infer_config = InferenceConfig()
        self.infer_service = infer_config.create_infer_client(profile="default")
        self.llm_model_name = infer_config.get_llm_model_name("default")
        logger.info("RAG、LLM客户端初始化完成")


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
