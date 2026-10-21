# app-server/src/com/damon/ming/db/db_connection.py
"""
数据库连接管理 —— SQLAlchemy 引擎 + 连接池 + 自动重连 + SQL 执行工具。

设计：
  - 使用 SQLAlchemy create_engine（自动管理连接池 QueuePool）
  - 支持 PostgreSQL / MySQL / SQLite 等多后端（通过 URL 自动识别驱动）
  - 原生 SQL 通过 text() 执行，可灵活使用各数据库特有语法（如 pgvector 的 <=>、::vector）
  - 对 %s 占位符（psycopg2/MySQL 风格）自动转为 SQLAlchemy :name 风格，业务层 SQL 零改动
  - 无业务语义，只负责"拿连接 → 执行 → 释放"
  - 连接失败自动重试（可配置重试次数和间隔）
"""

import threading
import time

from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.exception import DatabaseError
from src.com.damon.ming.log import pin

logger = pin("db.connection")


class DbConnection:
    """线程安全的通用数据库连接管理器（基于 SQLAlchemy）。

    支持通过同一套 API 操作 PostgreSQL / MySQL / SQLite 等，
    上层业务 SQL 无需改动（pgvector 等特殊语法通过 text() 原生执行）。

    用法：
      db = DbConnection(db_config)  # db_config 由上层配置加载器构造
      db.initialize()

      rows = db.execute("SELECT * FROM users WHERE id = %s", (user_id,), fetch=True)
      db.execute("INSERT INTO users (name) VALUES (%s)", (name,))
    """

    def __init__(self, config: DbConfig):
        self._config = config
        self._engine = None
        self._lock = threading.Lock()

    def initialize(self) -> None:
        """初始化 SQLAlchemy 引擎（连接池）。应用启动时调用一次。"""
        try:
            from sqlalchemy import create_engine, text

            url = self._config.get_sqlalchemy_url()
            kwargs = self._config.get_engine_kwargs()
            self._engine = create_engine(url, **kwargs)

            # 测试连接
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()

            logger.info(
                "数据库引擎初始化完成 | dialect=%s | url=%s | pool=%d+%d",
                self._config.dialect,
                _mask_url(url),
                self._config.pool_size,
                self._config.max_overflow,
            )
        except ImportError:
            from src.com.damon.ming.exception.error_codes import ErrorCode

            raise DatabaseError(
                "SQLAlchemy 未安装：pip install sqlalchemy",
                biz_code=ErrorCode.SYSTEM.DATABASE_FAILURE,
            )
        except Exception as e:
            logger.error("数据库引擎初始化失败: %s", e)
            raise

    def close(self) -> None:
        """关闭引擎，释放所有连接。应用退出时调用。"""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.info("数据库引擎已关闭")

    def execute(
        self,
        sql: str,
        params: tuple | dict | None = None,
        *,
        commit: bool = True,
        fetch: bool = False,
        retry: int | None = None,
    ) -> list[tuple] | None:
        """执行单条 SQL。

        支持原生 SQL 任意语法（如 pgvector 的 ::vector、<=> 操作符），
        SQLAlchemy 的 text() 会将其原样下发到数据库。
        对 %s 占位符自动转换，业务层无需修改 SQL。

        参数：
          sql:    SQL 语句（参数化，用 %s 或 :param 占位）
          params: 参数元组/列表或字典
          commit: 是否自动 commit（SELECT 用 False，INSERT/UPDATE 用 True）
          fetch:  是否返回查询结果（SELECT 用 True）
          retry:  连接失败时的重试次数（省略则用 DbConfig.retry_count）

        返回：
          fetch=True 时返回行列表（tuple 列表），否则返回 None
        """
        if self._engine is None:
            from src.com.damon.ming.exception.error_codes import ErrorCode

            raise DatabaseError(
                "DbConnection 未初始化。请先调用 initialize()。",
                biz_code=ErrorCode.SYSTEM.DATABASE_FAILURE,
            )

        from sqlalchemy import text

        retry = retry if retry is not None else self._config.retry_count
        backoff = self._config.backoff_seconds

        # 转换 %s 占位符为 SQLAlchemy 命名参数
        converted_sql, converted_params = _convert_placeholders(sql, params)

        last_error = None
        for attempt in range(retry):
            try:
                with self._engine.connect() as conn:
                    result = conn.execute(text(converted_sql), converted_params or {})
                    if commit:
                        conn.commit()
                    if fetch:
                        return [tuple(row) for row in result.fetchall()]
                    return None
            except Exception as e:
                last_error = e
                logger.warning(
                    "SQL 执行失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    retry,
                    e,
                )
                time.sleep(backoff * (attempt + 1))

        logger.error("SQL 执行最终失败 (已重试 %d 次): %s", retry, last_error)
        raise last_error

    def execute_many(
        self,
        sql: str,
        params_list: list[tuple | dict],
        *,
        commit: bool = True,
        retry: int | None = None,
    ) -> None:
        """批量执行同一条 SQL（不同参数）。"""
        if self._engine is None:
            from src.com.damon.ming.exception.error_codes import ErrorCode

            raise DatabaseError(
                "DbConnection 未初始化。请先调用 initialize()。",
                biz_code=ErrorCode.SYSTEM.DATABASE_FAILURE,
            )

        from sqlalchemy import text

        retry = retry if retry is not None else self._config.retry_count
        backoff = self._config.backoff_seconds

        last_error = None
        for attempt in range(retry):
            try:
                with self._engine.connect() as conn:
                    for params in params_list:
                        converted_sql, converted_params = _convert_placeholders(
                            sql, params
                        )
                        conn.execute(text(converted_sql), converted_params or {})
                    if commit:
                        conn.commit()
                    return
            except Exception as e:
                last_error = e
                logger.warning(
                    "SQL 批量执行失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    retry,
                    e,
                )
                time.sleep(backoff * (attempt + 1))

        raise last_error

    def transaction(self):
        """获取一个事务上下文管理器。

        用法：
          from sqlalchemy import text
          with db.transaction() as conn:
              conn.execute(text("INSERT INTO ... VALUES (:p0)"), {"p0": value})
              conn.execute(text("UPDATE ... SET ... WHERE ..."), {"p0": v1, "p1": v2})
          # 退出时自动 commit，异常时自动 rollback

        也可对 %s 占位符使用 execute 转换：
          with db.transaction() as conn:
              sql, params = _convert_placeholders("UPDATE ... SET x = %s WHERE y = %s", (x, y))
              conn.execute(text(sql), params)
        """
        return _TransactionContext(self)

    @property
    def engine(self):
        """暴露 SQLAlchemy 原生引擎，供需要直接操作的场景（如 pgvector_store）。"""
        return self._engine


class _TransactionContext:
    """事务上下文管理器。"""

    def __init__(self, db: DbConnection):
        self._db = db
        self.conn = None

    def __enter__(self):
        if self._db._engine is None:
            raise DatabaseError("DbConnection 未初始化")
        self.conn = self._db._engine.connect()
        self._txn = self.conn.begin()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._txn.commit()
            else:
                self._txn.rollback()
        finally:
            self.conn.close()
        return False


# ---------------------------------------------------------------------------
# 模块级便捷函数（使用全局默认实例）
# ---------------------------------------------------------------------------

_default_db: DbConnection | None = None


def get_default_db() -> DbConnection:
    """获取全局默认数据库连接。

    set_default_db 在 lifespan 启动阶段调用一次（早于任何请求），
    多 worker 场景下各进程独立初始化，无跨进程竞争。
    """
    if _default_db is None:
        from src.com.damon.ming.exception.error_codes import ErrorCode

        raise DatabaseError(
            "默认数据库未初始化。请先调用 set_default_db()。",
            biz_code=ErrorCode.SYSTEM.DATABASE_FAILURE,
        )
    return _default_db


def set_default_db(db: DbConnection) -> None:
    """设置全局默认数据库连接（在 lifespan 中调用一次）。"""
    global _default_db
    _default_db = db


def query(sql: str, params: tuple | dict | None = None) -> list[tuple]:
    """用默认连接执行查询，返回结果列表。"""
    return get_default_db().execute(sql, params, commit=False, fetch=True)


def execute(sql: str, params: tuple | dict | None = None) -> None:
    """用默认连接执行写操作。"""
    get_default_db().execute(sql, params, commit=True, fetch=False)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _convert_placeholders(
    sql: str, params: tuple | dict | None
) -> tuple[str, dict | None]:
    """将 SQL 中的 %s 占位符转换为 SQLAlchemy 命名参数。

    转换规则：
      - 无 params 或 params 为 dict → 原样返回（假定已用 :name 风格）
      - params 为 tuple/list → 将第 N 个 %s 替换为 :pN
    """
    if params is None:
        return sql, None

    if isinstance(params, dict):
        # 已经是 dict，假定 SQL 用 :name 占位符
        return sql, params

    # tuple / list → 转换 %s → :p0, :p1, ...
    if not isinstance(params, (tuple, list)):
        params = (params,)

    converted_params = {}
    parts = []
    param_index = 0
    i = 0
    sql_len = len(sql)
    while i < sql_len:
        if sql[i] == "%" and i + 1 < sql_len and sql[i + 1] == "s":
            parts.append(f":p{param_index}")
            converted_params[f"p{param_index}"] = params[param_index]  # type: ignore
            param_index += 1
            i += 2
        else:
            parts.append(sql[i])
            i += 1

    return "".join(parts), converted_params


def _mask_url(url: str) -> str:
    """脱敏 URL 中的密码部分（用于日志）。

    脱敏失败时返回占位符而非原始 URL，避免密码明文泄漏到日志。
    """
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        if parsed.password:
            masked = parsed._replace(
                netloc=f"{parsed.username}:***@{parsed.hostname}:{parsed.port}"
            )
            return urlunparse(masked)
        return url
    except Exception as e:
        logger.debug("URL 脱敏失败，已隐藏原始 URL | error=%s", e)
        return "<unprintable-url>"
