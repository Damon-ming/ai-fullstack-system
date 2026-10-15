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

存储：全部通过共享连接池持久化，服务重启后数据不丢失。
简单 CRUD 用 SQLAlchemy Core API（router/tables.py），
复杂语句（ON CONFLICT、事务内多步）仍用 raw SQL。
"""

import uuid
from datetime import timedelta

from sqlalchemy import text
from src.com.damon.ming.db.db_connection import get_default_db
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.tables.account import (
    DeviceRow,
    SessionRow,
    UserRow,
    devices,
    sessions,
    users,
)
from src.com.damon.ming.utils.time import now

logger = pin("account.store")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
# todo
SESSION_TTL = timedelta(days=30)  # 会话有效期


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _db():
    """获取默认数据库连接。"""
    return get_default_db()


# ---------------------------------------------------------------------------
# 用户（phone → token）
# ---------------------------------------------------------------------------


def get_token_by_phone(phone: str) -> str | None:
    """根据手机号查询已签发的 token。"""
    with _db().engine.connect() as conn:
        result = conn.execute(users.select().where(users.c.phone == phone))
        row = result.fetchone()
    return row.token if row else None


def get_phone_by_token(token: str) -> str | None:
    """根据 token 对应的手机号。"""
    with _db().engine.connect() as conn:
        result = conn.execute(users.select().where(users.c.token == token))
        row = result.fetchone()
    return row.phone if row else None


def is_token_valid(token: str) -> bool:
    """检查 token 是否存在。"""
    with _db().engine.connect() as conn:
        result = conn.execute(users.select().where(users.c.token == token))
        return result.fetchone() is not None


def bind_token(phone: str, token: str) -> None:
    """绑定 phone → token 映射（幂等，ON CONFLICT 覆盖）。"""
    _db().execute(
        "INSERT INTO users (token, phone, name, created_at) VALUES (%s, %s, '', %s) "
        "ON CONFLICT (token) DO UPDATE SET phone = EXCLUDED.phone",
        (token, phone, now()),
        commit=True,
    )


# ---------------------------------------------------------------------------
# 用户资料（token → UserRow）
# ---------------------------------------------------------------------------


def get_user_profile(token: str) -> UserRow | None:
    """根据 token 查询用户资料。"""
    with _db().engine.connect() as conn:
        result = conn.execute(users.select().where(users.c.token == token))
        row = result.fetchone()
    return UserRow(**row._mapping) if row else None


def update_user_name(token: str, name: str) -> bool:
    """更新用户昵称。返回是否成功。"""
    with _db().engine.connect() as conn:
        result = conn.execute(
            users.update()
            .where(users.c.token == token)
            .values(name=name)
        )
        conn.commit()
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# 设备（device_id → DeviceRow）
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

    如果 device_id 已存在，更新 UA 信息（UPSERT）。
    """
    _db().execute(
        "INSERT INTO devices (device_id, ua_hash, raw_ua, platform, screen, lang, tz, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (device_id) DO UPDATE SET "
        "ua_hash = EXCLUDED.ua_hash, raw_ua = EXCLUDED.raw_ua, "
        "platform = EXCLUDED.platform, screen = EXCLUDED.screen, "
        "lang = EXCLUDED.lang, tz = EXCLUDED.tz",
        (device_id, ua_hash, raw_ua, platform, screen, lang, tz, now()),
        commit=True,
    )


def get_device(device_id: str) -> DeviceRow | None:
    """查询设备记录。"""
    with _db().engine.connect() as conn:
        result = conn.execute(devices.select().where(devices.c.device_id == device_id))
        row = result.fetchone()
    if row is None:
        return None
    return DeviceRow(
        device_id=row.device_id,
        ua_hash=row.ua_hash,
        raw_ua=row.raw_ua or "",
        platform=row.platform or "",
        screen=row.screen or "",
        lang=row.lang or "",
        tz=row.tz or "",
        created_at=row.created_at,
    )


def is_device_registered(device_id: str) -> bool:
    """检查设备是否已注册。"""
    with _db().engine.connect() as conn:
        result = conn.execute(devices.select().where(devices.c.device_id == device_id))
        return result.fetchone() is not None


def remove_device(device_id: str) -> None:
    """删除设备记录（同时逻辑过期该设备的所有会话）。"""
    current = now()
    with _db().transaction() as conn:
        conn.execute(
            text(
                "UPDATE sessions SET expires_at = :now WHERE device_id = :did AND expires_at > :now"
            ),
            {"now": current, "did": device_id},
        )
        conn.execute(devices.delete().where(devices.c.device_id == device_id))


# ---------------------------------------------------------------------------
# 会话（session_id → SessionRow）
# ---------------------------------------------------------------------------


def create_session(token: str, device_id: str, ua_hash: str = "") -> str:
    """为 (token, device_id) 创建一个新会话。

    同一组合的旧会话立即过期（确保每个 token+device 只有一条活跃会话）。
    返回新 session_id。
    """
    current = now()
    session_id = str(uuid.uuid4())
    expires_at = current + SESSION_TTL

    with _db().transaction() as conn:
        # 过期旧会话
        conn.execute(
            text(
                "UPDATE sessions SET expires_at = :now WHERE token = :tok AND device_id = :did AND expires_at > :now"
            ),
            {"now": current, "tok": token, "did": device_id},
        )
        # 插入新会话
        conn.execute(
            sessions.insert().values(
                session_id=session_id,
                token=token,
                device_id=device_id,
                issued_ua_hash=ua_hash,
                created_at=current,
                expires_at=expires_at,
            )
        )

    return session_id


def get_session(session_id: str) -> SessionRow | None:
    """查询有效会话（未过期）。"""
    current = now()
    with _db().engine.connect() as conn:
        result = conn.execute(
            sessions.select().where(
                sessions.c.session_id == session_id,
                sessions.c.expires_at > current,
            )
        )
        row = result.fetchone()
    return _session_row(row)


def get_active_session(token: str, device_id: str) -> SessionRow | None:
    """查询某 (token, device_id) 的活跃会话。"""
    current = now()
    with _db().engine.connect() as conn:
        result = conn.execute(
            sessions.select().where(
                sessions.c.token == token,
                sessions.c.device_id == device_id,
                sessions.c.expires_at > current,
            )
        )
        row = result.fetchone()
    return _session_row(row)


def revoke_sessions_by_token(token: str) -> int:
    """注销某 token 的所有会话。返回注销数量。"""
    current = now()
    with _db().transaction() as conn:
        result = conn.execute(
            text(
                "UPDATE sessions SET expires_at = :now WHERE token = :tok AND expires_at > :now"
            ),
            {"now": current, "tok": token},
        )
        return result.rowcount


def revoke_sessions_by_device(device_id: str) -> int:
    """注销某设备的所有会话。返回注销数量。"""
    current = now()
    with _db().transaction() as conn:
        result = conn.execute(
            text(
                "UPDATE sessions SET expires_at = :now WHERE device_id = :did AND expires_at > :now"
            ),
            {"now": current, "did": device_id},
        )
        return result.rowcount


# ---------------------------------------------------------------------------
# 调试 / 管理
# ---------------------------------------------------------------------------


def get_all_devices() -> list[DeviceRow]:
    """获取所有设备记录副本（调试用）。"""
    with _db().engine.connect() as conn:
        result = conn.execute(devices.select())
        rows = result.fetchall()
    return [
        DeviceRow(
            device_id=r.device_id,
            ua_hash=r.ua_hash,
            raw_ua=r.raw_ua or "",
            platform=r.platform or "",
            screen=r.screen or "",
            lang=r.lang or "",
            tz=r.tz or "",
            created_at=r.created_at,
        )
        for r in (rows or [])
    ]


def get_all_sessions() -> list[SessionRow]:
    """获取所有有效会话副本（调试用）。"""
    current = now()
    with _db().engine.connect() as conn:
        result = conn.execute(sessions.select().where(sessions.c.expires_at > current))
        rows = result.fetchall()
    return [_session_row(r) for r in (rows or [])]


def get_stats() -> dict:
    """获取统计信息。"""
    current = now()
    with _db().engine.connect() as conn:
        users_count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
        devices_count = conn.execute(text("SELECT COUNT(*) FROM devices")).scalar() or 0
        sessions_count = (
            conn.execute(
                text("SELECT COUNT(*) FROM sessions WHERE expires_at > :now"),
                {"now": current},
            ).scalar()
            or 0
        )
    return {
        "users": users_count,
        "devices": devices_count,
        "sessions": sessions_count,
    }


# ---------------------------------------------------------------------------
# 行映射工具
# ---------------------------------------------------------------------------


def _session_row(row) -> SessionRow | None:
    """将查询结果映射为 SessionRow。"""
    if row is None:
        return None
    return SessionRow(
        session_id=row.session_id,
        token=row.token,
        device_id=row.device_id,
        issued_ua_hash=row.issued_ua_hash or "",
        created_at=row.created_at,
        expires_at=row.expires_at,
    )
