# app-server/src/com/damon/ming/router/account/token_store.py
"""
身份 + 设备 + 会话 存储层。

职责分离：
  - phone → users.user_id：稳定的内部用户 ID（不下发客户端）
  - device_id：设备层（独立存在，不归属任何用户）
  - session_id：服务端内部会话标识，保存单个设备凭据摘要

关联关系：
  phone ──1:1── users.user_id   （稳定用户 ID）
  device_id ──独立注册           （设备身份，不绑定用户）
  (users.user_id, device_id) ──1:1── session_id（每次登录产生一个会话）

存储：全部通过共享连接池持久化，服务重启后数据不丢失。
CRUD 使用 SQLAlchemy Core 复用 app/tables 的表定义，
UPSERT 使用 PostgreSQL 方言，行锁与多步写入保留在同一事务中。
"""

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.com.damon.ming.app.tables.account_tables import (
    UserRow,
    devices,
    sessions,
    users,
)
from src.com.damon.ming.db import get_default_db
from src.com.damon.ming.exception import DatabaseError
from src.com.damon.ming.log import pin
from src.com.damon.ming.security import (
    generate_session_token,
    hash_password,
    verify_password,
)
from src.com.damon.ming.security.digest import sha256_hex
from src.com.damon.ming.utils.time import now
from src.com.damon.ming.utils.uuid import generate_uuid

logger = pin("account.store")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SESSION_IDLE_TTL = timedelta(days=7)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _db():
    """获取默认数据库连接。"""
    return get_default_db()


# ---------------------------------------------------------------------------
# 用户（phone → user_id）
# ---------------------------------------------------------------------------


def _login_existing_user(phone: str, password: str) -> int | None:
    """验证密码并返回稳定的内部用户标识。"""
    with _db().transaction() as conn:
        row = conn.execute(
            users.select().where(users.c.phone == phone).with_for_update()
        ).fetchone()
        if row is None:
            return None

        _verify_user_password(row, password)
        return row.user_id


def get_phone_by_user_id(user_id: int) -> str | None:
    """根据内部用户 ID 查询手机号。"""
    with _db().engine.connect() as conn:
        result = conn.execute(users.select().where(users.c.user_id == user_id))
        row = result.fetchone()
    return row.phone if row else None


def _verify_user_password(row, password: str) -> None:
    """验证用户密码。"""
    if not verify_password(password, row.password):
        raise ValueError("PHONE_PASSWORD_MISMATCH")


def _generate_default_name() -> str:
    """生成随机默认昵称：用户_XXXX（4位 hex）。"""
    return f"用户_{secrets.token_hex(2).upper()}"


def login_or_register(phone: str, password: str) -> tuple[int, bool]:
    """登录或自动注册，返回 (内部用户 ID, is_new)。

    流程：
      1. phone 已注册 → 验 password → 对则返回 (user_id, False)
      2. phone 未注册且插入成功 → 返回 (新 user_id, True)
      3. 并发请求先插入同一 phone → 校验已有账号密码后返回 (user_id, False)
    """
    existing_user_id = _login_existing_user(phone, password)
    if existing_user_id is not None:
        return existing_user_id, False

    # 新用户 → 自动注册（生成随机默认昵称）
    password_hash = hash_password(password)
    default_name = _generate_default_name()
    with _db().transaction() as conn:
        inserted = conn.execute(
            pg_insert(users)
            .values(
                phone=phone,
                password=password_hash,
                name=default_name,
                created_at=now(),
            )
            .on_conflict_do_nothing(index_elements=[users.c.phone])
            .returning(users.c.user_id)
        ).fetchone()
    if inserted is not None:
        return inserted.user_id, True

    # 并发请求可能已先为该手机号创建账号；冲突方必须验证密码，
    # 不能把竞争者的 user_id 当作本次注册成功结果返回。
    existing_user_id = _login_existing_user(phone, password)
    if existing_user_id is None:
        raise DatabaseError("用户注册冲突后未能查询到手机号记录")
    return existing_user_id, False


# ---------------------------------------------------------------------------
# 用户资料（user_id → UserRow）
# ---------------------------------------------------------------------------


def get_user_profile(user_id: int) -> UserRow | None:
    """根据 user_id 查询用户资料。"""
    with _db().engine.connect() as conn:
        result = conn.execute(users.select().where(users.c.user_id == user_id))
        row = result.fetchone()
    return UserRow(**row._mapping) if row else None


def update_user_name(user_id: int, name: str) -> bool:
    """更新用户昵称。返回是否成功。"""
    with _db().engine.connect() as conn:
        result = conn.execute(
            users.update().where(users.c.user_id == user_id).values(name=name)
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
) -> None:
    """注册一台设备。设备身份独立存在，不归属任何用户。

    如果 device_id 已存在，更新 UA 信息（UPSERT）。
    """
    statement = pg_insert(devices).values(
        device_id=device_id,
        ua_hash=ua_hash,
        raw_ua=raw_ua,
        created_at=now(),
    )
    _db().execute(
        statement.on_conflict_do_update(
            index_elements=[devices.c.device_id],
            set_={
                column: statement.excluded[column.name]
                for column in (devices.c.ua_hash, devices.c.raw_ua)
            },
            where=devices.c.ua_hash != statement.excluded.ua_hash,
        ),
        commit=True,
    )


# ---------------------------------------------------------------------------
# 会话（单个 token → 设备会话）
# ---------------------------------------------------------------------------


def create_session(user_id: int, device_id: str) -> str:
    """创建新会话，只向客户端返回一个随机 token。

    每次登录都返回新 session_id，消除 get-then-create 的 TOCTOU 窗口。
    通过 SELECT ... FOR UPDATE 锁住 device 行串行化同一设备的并发登录，
    确保最终只有一条活跃 session。
    """
    current = now()
    session_id = generate_uuid()
    token = generate_session_token()
    expires_at = current + SESSION_IDLE_TTL

    with _db().transaction() as conn:
        # 锁住 device 行，串行化同一设备的并发登录，防止新 session 被并发 UPDATE 过期
        conn.execute(
            select(devices.c.device_id)
            .where(devices.c.device_id == device_id)
            .with_for_update()
        )
        # 过期该 (user_id, device_id) 的所有旧会话
        conn.execute(
            sessions.update()
            .where(
                sessions.c.user_id == user_id,
                sessions.c.device_id == device_id,
                sessions.c.expires_at > current,
            )
            .values(expires_at=current)
        )
        # 插入新会话
        conn.execute(
            sessions.insert().values(
                session_id=session_id,
                user_id=user_id,
                device_id=device_id,
                created_at=current,
                expires_at=expires_at,
                token=sha256_hex(token),
            )
        )

    return token


def authenticate_token(token: str, device_id: str) -> tuple[int, str] | None:
    """匹配 token 所属设备后原子续期，返回 (user_id, session_id)。"""
    current = now()
    with _db().transaction() as conn:
        row = conn.execute(
            sessions.update()
            .where(
                sessions.c.token == sha256_hex(token),
                sessions.c.device_id == device_id,
                sessions.c.expires_at > current,
            )
            .values(expires_at=current + SESSION_IDLE_TTL)
            .returning(sessions.c.user_id, sessions.c.session_id)
        ).fetchone()
    return (row.user_id, row.session_id) if row else None


def revoke_session(session_id: str) -> None:
    """撤销当前设备会话；后续请求不能再使用该 token。"""
    _db().execute(
        sessions.update()
        .where(sessions.c.session_id == session_id)
        .values(expires_at=now()),
        commit=True,
    )
