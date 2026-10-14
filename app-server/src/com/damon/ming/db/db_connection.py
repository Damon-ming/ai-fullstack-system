# app-server/src/com/damon/ming/db/db_connection.py
"""
数据库连接管理 —— 连接池 + 自动重连 + SQL 执行工具。

设计：
  - 使用 psycopg2 原生连接池（ThreadedConnectionPool）
  - 无业务语义，只负责"拿连接 → 执行 → 归还"
  - 连接失败自动重试（可配置重试次数和间隔）
"""

import threading
import time

from src.com.damon.ming.db.db_config import DbConfig
from src.com.damon.ming.exception import DatabaseError
from src.com.damon.ming.log import pin

logger = pin("db.connection")


class DbConnection:
    """线程安全的 PostgreSQL 连接管理器。

    用法：
      db = DbConnection(DbConfig.from_env())
      db.initialize(min_conn=1, max_conn=5)

      rows = query("SELECT * FROM users WHERE id = %s", (user_id,))
      execute("INSERT INTO users (name) VALUES (%s)", (name,))
    """

    def __init__(self, config: DbConfig):
        self._config = config
        self._pool = None
        self._local = threading.local()
        self._lock = threading.Lock()

    def initialize(self, min_conn: int | None = None, max_conn: int | None = None) -> None:
        """初始化连接池。应用启动时调用一次。

        参数省略时从 DbConfig 读取（由上层 YAML 配置或环境变量注入）。
        """
        min_conn = min_conn if min_conn is not None else self._config.pool_min
        max_conn = max_conn if max_conn is not None else self._config.pool_max

        try:
            from psycopg2 import pool

            self._pool = pool.ThreadedConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                dsn=self._config.get_connection_string(),
                **self._config.connect_kwargs,
            )
            logger.info(
                "数据库连接池初始化完成 | host=%s | db=%s | pool=%d-%d",
                self._config.host or "from_url",
                self._config.dbname or "from_url",
                min_conn,
                max_conn,
            )
        except ImportError:
            from src.com.damon.ming.exception.error_codes import ErrorCode

            raise DatabaseError(
                "psycopg2 未安装：pip install psycopg2-binary",
                biz_code=ErrorCode.SYSTEM.DATABASE_FAILURE,
            )
        except Exception as e:
            logger.error("数据库连接池初始化失败: %s", e)
            raise

    def _get_conn(self):
        """从连接池获取连接。"""
        if self._pool is None:
            from src.com.damon.ming.exception.error_codes import ErrorCode

            raise DatabaseError(
                "DbConnection 未初始化。请先调用 initialize()。",
                biz_code=ErrorCode.SYSTEM.DATABASE_FAILURE,
            )
        return self._pool.getconn()

    def _return_conn(self, conn) -> None:
        """归还连接到连接池。"""
        if self._pool is not None:
            self._pool.putconn(conn)

    def close(self) -> None:
        """关闭所有连接。应用退出时调用。"""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None
            logger.info("数据库连接池已关闭")

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

        参数：
          sql:    SQL 语句（参数化，用 %s 占位）
          params: 参数元组或字典
          commit: 是否自动 commit（SELECT 用 False，INSERT/UPDATE 用 True）
          fetch:  是否返回查询结果（SELECT 用 True）
          retry:  连接失败时的重试次数（省略则用 DbConfig.retry_count）

        返回：
          fetch=True 时返回行列表，否则返回 None
        """
        retry = retry if retry is not None else self._config.retry_count
        backoff = self._config.backoff_seconds

        last_error = None
        for attempt in range(retry):
            conn = None
            try:
                conn = self._get_conn()
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    result = cur.fetchall() if fetch else None
                if commit:
                    conn.commit()
                return result
            except Exception as e:
                last_error = e
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                logger.warning(
                    "SQL 执行失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    retry,
                    e,
                )
                time.sleep(backoff * (attempt + 1))
            finally:
                if conn is not None:
                    self._return_conn(conn)

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
        retry = retry if retry is not None else self._config.retry_count
        backoff = self._config.backoff_seconds

        last_error = None
        for attempt in range(retry):
            conn = None
            try:
                conn = self._get_conn()
                with conn.cursor() as cur:
                    cur.executemany(sql, params_list)
                if commit:
                    conn.commit()
                return
            except Exception as e:
                last_error = e
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                time.sleep(backoff * (attempt + 1))
            finally:
                if conn is not None:
                    self._return_conn(conn)

        raise last_error

    def transaction(self):
        """获取一个事务上下文管理器。

        用法：
          with db.transaction() as conn:
              with conn.cursor() as cur:
                  cur.execute("INSERT ...", ...)
                  cur.execute("UPDATE ...", ...)
          # 退出时自动 commit，异常时自动 rollback
        """
        return _TransactionContext(self)


class _TransactionContext:
    """事务上下文管理器。"""

    def __init__(self, db: DbConnection):
        self._db = db
        self.conn = None

    def __enter__(self):
        self.conn = self._db._get_conn()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self._db._return_conn(self.conn)
        return False


# ---------------------------------------------------------------------------
# 模块级便捷函数（使用全局默认实例）
# ---------------------------------------------------------------------------

_default_db: DbConnection | None = None
_default_db_lock = threading.Lock()


def get_default_db() -> DbConnection:
    """获取全局默认数据库连接。"""
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
    with _default_db_lock:
        _default_db = db


def query(sql: str, params: tuple | dict | None = None) -> list[tuple]:
    """用默认连接执行查询，返回结果列表。"""
    return get_default_db().execute(sql, params, commit=False, fetch=True)


def execute(sql: str, params: tuple | dict | None = None) -> None:
    """用默认连接执行写操作。"""
    get_default_db().execute(sql, params, commit=True, fetch=False)
