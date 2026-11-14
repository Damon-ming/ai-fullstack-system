"""字段加密密钥的数据库存储。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.com.damon.ming.app.tables.encryption_tables import field_encryption_keys_table
from src.com.damon.ming.db.db_connection import DbConnection
from src.com.damon.ming.encryption.v1.crypto_engine import AesGcmEngine, CryptoEngine


class PgFieldKeyStore:
    """持久化活动数据密钥和盲索引密钥（数据库明文）。"""

    def __init__(self, db_connection: DbConnection) -> None:
        self._db = db_connection

    def load_or_create(self) -> tuple[bytes, bytes]:
        table = field_encryption_keys_table
        with self._db.engine.begin() as conn:
            row = conn.execute(select(table).where(table.c.id == 1)).mappings().first()
            if row is None:
                statement = pg_insert(table).values(
                    id=1,
                    data_key=AesGcmEngine.generate_key(),
                    index_key=CryptoEngine.generate_blind_index_key(),
                )
                conn.execute(
                    statement.on_conflict_do_nothing(index_elements=[table.c.id])
                )
                row = (
                    conn.execute(select(table).where(table.c.id == 1)).mappings().one()
                )
            return bytes(row["data_key"]), bytes(row["index_key"])
