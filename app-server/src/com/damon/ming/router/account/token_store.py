# app-server/src/com/damon/ming/router/account/token_store.py
"""
身份 + 设备 + 会话 存储层。

职责分离：
  - phone → token：用户身份层（1:1，幂等）
  - device_id：设备层（独立存在，不归属任何用户）
  - session_id：会话层（token + device_id 的唯一组合）

关联关系：
  phone ──1:1── token           （一个用户一个身份令牌）
  device_id ──独立注册           （设备身份，不绑定用户）
  (token, device_id) ──1:1── session_id  （每次 token 签发产生一个会话）

存储：全部通过 PostgreSQL 持久化，服务重启后数据不丢失。
SQL 语句在 sql/ 子目录各表对应文件，本文件只负责业务逻辑和调用。
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.com.damon.ming.db.db_connection import get_default_db
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.account.sql import devices_sql, sessions_sql, users_sql

logger = pin("account.store")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SESSION_TTL = timedelta(days=30)  # 会话有效期


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class DeviceRecord:
    """一台已注册设备的信息。"""

    device_id: str
    ua_hash: str
    raw_ua: str = ""
    platform: str = ""
    screen: str = ""
    lang: str = ""
    tz: str = ""
    created_at: datetime | None = None


@dataclass
class SessionRecord:
    """一个会话实例（token + device_id 的唯一组合）。"""

    session_id: str
    token: str
    device_id: str
    ua_hash: str
    created_at: datetime | None = None
    expires_at: datetime | None = None


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _db():
    """获取默认数据库连接。"""
    return get_default_db()


def _now() -> datetime:
    return datetime.now(UTC)


def _session_row_to_record(row: tuple) -> SessionRecord:
    return SessionRecord(
        session_id=row[0],
        token=row[1],
        device_id=row[2],
        ua_hash=row[3],
        created_at=row[4],
        expires_at=row[5],
    )


def _device_row_to_record(row: tuple) -> DeviceRecord:
    return DeviceRecord(
        device_id=row[0],
        ua_hash=row[1],
        raw_ua=row[2],
        platform=row[3],
        screen=row[4],
        lang=row[5],
        tz=row[6],
        created_at=row[7],
    )


# ---------------------------------------------------------------------------
# 用户（phone → token）
# ---------------------------------------------------------------------------


def get_token_by_phone(phone: str) -> str | None:
    """根据手机号查询已签发的 token。"""
    rows = _db().execute(
        users_sql.GET_TOKEN_BY_PHONE, (phone,), commit=False, fetch=True
    )
    return rows[0][0] if rows else None


def get_phone_by_token(token: str) -> str | None:
    """根据 token 查询对应的手机号。"""
    rows = _db().execute(
        users_sql.GET_PHONE_BY_TOKEN, (token,), commit=False, fetch=True
    )
    return rows[0][0] if rows else None


def is_token_valid(token: str) -> bool:
    """检查 token 是否存在。"""
    rows = _db().execute(
        users_sql.GET_PHONE_BY_TOKEN, (token,), commit=False, fetch=True
    )
    return len(rows or []) > 0


def bind_token(phone: str, token: str) -> None:
    """绑定 phone → token 映射（幂等）。"""
    _db().execute(users_sql.INSERT, (token, phone, _now()), commit=True)


# ---------------------------------------------------------------------------
# 设备（device_id → DeviceRecord）
# ---------------------------------------------------------------------------


def register_device(
    device_id: str,
    ua_hash: str,
    raw_ua: str = "",
    platform: str = "",
    screen: str = "",
    lang: str = "",
    tz: str = "",
) -> None:
    """注册一台设备。设备身份独立存在，不归属任何用户。

    如果 device_id 已存在，更新 UA 信息。
    """
    _db().execute(
        devices_sql.UPSERT,
        (device_id, ua_hash, raw_ua, platform, screen, lang, tz, _now()),
        commit=True,
    )


def get_device(device_id: str) -> DeviceRecord | None:
    """查询设备记录。"""
    rows = _db().execute(devices_sql.GET, (device_id,), commit=False, fetch=True)
    return _device_row_to_record(rows[0]) if rows else None


def is_device_registered(device_id: str) -> bool:
    """检查设备是否已注册。"""
    rows = _db().execute(devices_sql.GET, (device_id,), commit=False, fetch=True)
    return len(rows or []) > 0


def remove_device(device_id: str) -> None:
    """删除设备记录（同时逻辑过期该设备的所有会话）。"""
    _db().execute(sessions_sql.REVOKE_BY_DEVICE, (device_id,), commit=True)
    _db().execute(devices_sql.DELETE, (device_id,), commit=True)


# ---------------------------------------------------------------------------
# 会话（session_id → SessionRecord）
# ---------------------------------------------------------------------------


def create_session(token: str, device_id: str, ua_hash: str = "") -> str:
    """为 (token, device_id) 创建一个新会话。

    同一组合的旧会话立即过期（确保每个 token+device 只有一条活跃会话）。
    返回新 session_id。
    """
    now = _now()
    session_id = str(uuid.uuid4())
    expires_at = now + SESSION_TTL

    with _db().transaction() as conn, conn.cursor() as cur:
        cur.execute(sessions_sql.EXPIRE_OLD, (now, token, device_id, now))
        cur.execute(
            sessions_sql.INSERT,
            (session_id, token, device_id, ua_hash, now, expires_at),
        )

    return session_id


def get_session(session_id: str) -> SessionRecord | None:
    """查询有效会话（未过期）。"""
    rows = _db().execute(
        sessions_sql.GET,
        (session_id, _now()),
        commit=False,
        fetch=True,
    )
    return _session_row_to_record(rows[0]) if rows else None


def get_active_session(token: str, device_id: str) -> SessionRecord | None:
    """查询某 (token, device_id) 的活跃会话。"""
    rows = _db().execute(
        sessions_sql.GET_ACTIVE,
        (token, device_id, _now()),
        commit=False,
        fetch=True,
    )
    return _session_row_to_record(rows[0]) if rows else None


def revoke_sessions_by_token(token: str) -> int:
    """注销某 token 的所有会话。返回注销数量。"""
    now = _now()
    from sqlalchemy import text
    from src.com.damon.ming.db.db_connection import _convert_placeholders

    with _db().transaction() as conn:
        sql, params = _convert_placeholders(sessions_sql.REVOKE_BY_TOKEN, (now, token, now))
        result = conn.execute(text(sql), params)
        count = result.rowcount
    return count


def revoke_sessions_by_device(device_id: str) -> int:
    """注销某设备的所有会话。返回注销数量。"""
    now = _now()
    from sqlalchemy import text
    from src.com.damon.ming.db.db_connection import _convert_placeholders

    with _db().transaction() as conn:
        sql, params = _convert_placeholders(sessions_sql.REVOKE_BY_DEVICE, (now, device_id, now))
        result = conn.execute(text(sql), params)
        count = result.rowcount
    return count


# ---------------------------------------------------------------------------
# 调试 / 管理
# ---------------------------------------------------------------------------


def get_all_devices() -> list[DeviceRecord]:
    """获取所有设备记录副本（调试用）。"""
    rows = _db().execute(devices_sql.GET_ALL, commit=False, fetch=True)
    return [_device_row_to_record(r) for r in (rows or [])]


def get_all_sessions() -> list[SessionRecord]:
    """获取所有有效会话副本（调试用）。"""
    rows = _db().execute(
        sessions_sql.GET_ALL,
        (_now(),),
        commit=False,
        fetch=True,
    )
    return [_session_row_to_record(r) for r in (rows or [])]


def get_stats() -> dict:
    """获取统计信息。"""
    user_rows = _db().execute(users_sql.COUNT, commit=False, fetch=True)
    device_rows = _db().execute(devices_sql.COUNT, commit=False, fetch=True)
    session_rows = _db().execute(
        sessions_sql.COUNT,
        (_now(),),
        commit=False,
        fetch=True,
    )
    return {
        "users": user_rows[0][0] if user_rows else 0,
        "devices": device_rows[0][0] if device_rows else 0,
        "sessions": session_rows[0][0] if session_rows else 0,
    }
