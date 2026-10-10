# app-server/src/com/damon/ming/db/db_migration.py
"""
数据库迁移工具 —— 纯技术模块，管理表结构版本。

设计：
  - 每个迁移有一个唯一 ID 和对应的 SQL（DDL）
  - 已执行的迁移记录在 _migrations 表中，幂等（重复执行不报错）
  - 业务层定义迁移内容，本模块只负责执行和追踪

用法：
    from src.com.damon.ming.db import DbConnection, DbMigration

    db = DbConnection(config)
    db.initialize()

    migration = DbMigration(db)

    migration.register("001_create_users", '''
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    ''')

    migration.apply_all()
"""

import hashlib
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationRecord:
    """一条迁移记录。"""

    migration_id: str
    applied_sql: str


class DbMigration:
    """数据库迁移管理器。"""

    _MIGRATION_TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS _migrations (
        migration_id  VARCHAR(128) PRIMARY KEY,
        applied_at    TIMESTAMP DEFAULT NOW(),
        sql_hash      VARCHAR(64)  NOT NULL
    );
    """

    _CHECK_APPLIED = """
    SELECT 1 FROM _migrations WHERE migration_id = %s;
    """

    _RECORD_APPLIED = """
    INSERT INTO _migrations (migration_id, sql_hash)
    VALUES (%s, %s)
    ON CONFLICT (migration_id) DO NOTHING;
    """

    def __init__(self, db_connection) -> None:
        self._db = db_connection
        self._migrations: dict[str, str] = {}
        self._lock = threading.Lock()

    def register(self, migration_id: str, sql: str) -> None:
        """注册一条迁移。

        参数：
          migration_id: 唯一标识（如 "001_create_sessions"）
          sql:          DDL 语句
        """
        self._migrations[migration_id] = sql

    def apply_all(self) -> int:
        """执行所有未应用的迁移。返回本次应用的迁移数量。"""
        self._db.execute(self._MIGRATION_TABLE_DDL, commit=True)

        applied_count = 0
        with self._lock:
            for migration_id, sql in self._migrations.items():
                if self._is_applied(migration_id):
                    continue

                self._db.execute(sql, commit=True)

                sql_hash = self._hash_sql(sql)
                self._db.execute(
                    self._RECORD_APPLIED,
                    (migration_id, sql_hash),
                )
                applied_count += 1

        return applied_count

    def _is_applied(self, migration_id: str) -> bool:
        """检查迁移是否已应用。"""
        rows = self._db.execute(
            self._CHECK_APPLIED,
            (migration_id,),
            commit=False,
            fetch=True,
        )
        return len(rows or []) > 0

    @staticmethod
    def _hash_sql(sql: str) -> str:
        """计算 SQL 的哈希（用于检测迁移内容是否被篡改）。"""
        return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16]
