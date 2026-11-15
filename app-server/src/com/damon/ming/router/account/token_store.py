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
CRUD 使用 SQLAlchemy Core 复用 app/tables 的表定义，
UPSERT 使用 PostgreSQL 方言，行锁与多步写入保留在同一事务中。
"""

import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.com.damon.ming.app.tables.account_tables import (
    SessionRow,
    UserRow,
    devices,
    sessions,
    users,
)
from src.com.damon.ming.app.tables.upload_tables import upload_records
from src.com.damon.ming.db import get_default_db
from src.com.damon.ming.exception import DatabaseError
from src.com.damon.ming.log import pin
from src.com.damon.ming.security import (
    hash_password,
    verify_password,
)
from src.com.damon.ming.utils.time import now
from src.com.damon.ming.utils.uuid import generate_uuid

logger = pin("account.store")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
# SECURITY: token TTL 常量（P1-7 修复）
SESSION_TTL = timedelta(days=30)  # 会话有效期
TOKEN_TTL = timedelta(days=30)  # token 滚动过期：30 天不活跃则失效
TOKEN_HARD_TTL = timedelta(days=90)  # token 绝对过期：90 天强制重新登录

# 首次部署时执行一次迁移（已有 users 表无 expires_at 列）：
#   ALTER TABLE users
#     ADD COLUMN expires_at TIMESTAMP NOT NULL DEFAULT NOW() + INTERVAL '30 days',
#     ADD COLUMN hard_expires_at TIMESTAMP NOT NULL DEFAULT NOW() + INTERVAL '90 days';


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _db():
    """获取默认数据库连接。"""
    return get_default_db()


# ---------------------------------------------------------------------------
# 用户（phone → token）
# ---------------------------------------------------------------------------


def _get_user_by_phone(phone: str):
    with _db().engine.connect() as conn:
        result = conn.execute(users.select().where(users.c.phone == phone))
        return result.fetchone()


def get_phone_by_token(token: str) -> str | None:
    """根据 token 对应的手机号。"""
    with _db().engine.connect() as conn:
        result = conn.execute(users.select().where(users.c.token == token))
        row = result.fetchone()
    return row.phone if row else None


def is_token_valid(token: str) -> bool:
    """检查 token 是否存在且未过期（滚动 TTL + 绝对 TTL 双重检查）。"""
    with _db().engine.connect() as conn:
        result = conn.execute(
            users.select().where(
                users.c.token == token,
                users.c.expires_at > func.now(),
                users.c.hard_expires_at > func.now(),
            )
        )
        return result.fetchone() is not None


def _verify_user_password(row, password: str) -> None:
    """验证用户密码。"""
    if not verify_password(password, row.password):
        raise ValueError("PHONE_PASSWORD_MISMATCH")


def _generate_default_name() -> str:
    """生成随机默认昵称：用户_XXXX（4位 hex）。"""
    return f"用户_{secrets.token_hex(2).upper()}"


def login_or_register(phone: str, password: str) -> tuple[str, bool]:
    """登录或自动注册，返回 (token, is_new)。

    流程：
      1. phone 已注册 → 验 password → 对则返回 (token, False)，错则抛 ValueError
      2. phone 未注册且插入成功 → 返回 (新 token, True)
      3. 并发请求先插入同一 phone → 校验已有账号密码后返回 (token, False)
    """
    existing_user = _get_user_by_phone(phone)
    if existing_user is not None:
        _verify_user_password(existing_user, password)
        return existing_user.token, False

    # 新用户 → 自动注册（生成随机默认昵称）
    new_token = secrets.token_hex(32)
    password_hash = hash_password(password)
    default_name = _generate_default_name()
    inserted_rows = _db().execute(
        pg_insert(users)
        .values(
            token=new_token,
            phone=phone,
            password=password_hash,
            name=default_name,
            created_at=now(),
            expires_at=func.now() + TOKEN_TTL,
            hard_expires_at=func.now() + TOKEN_HARD_TTL,
        )
        .on_conflict_do_nothing(index_elements=[users.c.phone]),
        commit=True,
    )
    if inserted_rows == 1:
        return new_token, True
    if inserted_rows != 0:
        raise DatabaseError("无法确认用户注册写入结果")

    # 并发请求可能已先为该手机号创建账号；冲突方必须验证密码，
    # 不能把竞争者的 token 当作本次注册成功结果返回。
    row = _get_user_by_phone(phone)
    if row is None:
        raise DatabaseError("用户注册冲突后未能查询到手机号记录")
    _verify_user_password(row, password)
    return row.token, False


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
            users.update().where(users.c.token == token).values(name=name)
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
# 会话（session_id → SessionRow）
# ---------------------------------------------------------------------------


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


def create_or_refresh_session(token: str, device_id: str) -> str:
    """创建新会话并原子过期该 (token, device_id) 的所有旧会话。

    每次登录都返回新 session_id，消除 get-then-create 的 TOCTOU 窗口。
    通过 SELECT ... FOR UPDATE 锁住 device 行串行化同一设备的并发登录，
    确保最终只有一条活跃 session。
    """
    current = now()
    session_id = generate_uuid()
    expires_at = current + SESSION_TTL

    with _db().transaction() as conn:
        # 锁住 device 行，串行化同一设备的并发登录，防止新 session 被并发 UPDATE 过期
        conn.execute(
            select(devices.c.device_id)
            .where(devices.c.device_id == device_id)
            .with_for_update()
        )
        # 过期该 (token, device_id) 的所有旧会话
        conn.execute(
            sessions.update()
            .where(
                sessions.c.token == token,
                sessions.c.device_id == device_id,
                sessions.c.expires_at > current,
            )
            .values(expires_at=current)
        )
        # 插入新会话
        conn.execute(
            sessions.insert().values(
                session_id=session_id,
                token=token,
                device_id=device_id,
                created_at=current,
                expires_at=expires_at,
            )
        )

    return session_id


def refresh_token_ttl(token: str) -> None:
    """刷新 token 的滚动过期时间（登录成功时调用）。

    仅更新 expires_at（滚动 TTL），不更新 hard_expires_at（绝对 TTL）。
    即使用户持续活跃，90 天后也必须重新登录。

    TODO: 当前 token 值不变（phone 1:1 绑定），仅靠 TTL 兜底。
      若要缩短被盗窗口至"下次登录即失效"，需引入多 token 表：
      新建 tokens 表 (token, phone, device_id, expires_at, hard_expires_at)，
      每次登录生成新 token 行不覆盖旧值，各设备独立持有 token。
      届时 refresh_token_ttl 改为 INSERT 新行 + 清理过期行，
      is_token_valid 改为查 tokens 表。
    """
    _db().execute(
        users.update()
        .where(users.c.token == token)
        .values(expires_at=func.now() + TOKEN_TTL),
        commit=True,
    )


# ---------------------------------------------------------------------------
# 跨模块查询 —— 供其他模块调用，不暴露表结构
# ---------------------------------------------------------------------------


def get_file_uploader_map() -> dict[str, str]:
    """查询所有文件的上传者昵称，返回 {file_path: uploader_name}。

    供知识库等模块调用，调用方无需感知 upload_records / users 表结构。
    """

    try:
        with _db().engine.connect() as conn:
            rows = conn.execute(
                select(upload_records.c.file_path, users.c.name).select_from(
                    upload_records.outerjoin(
                        users, upload_records.c.token == users.c.token
                    )
                )
            ).fetchall()
        return {row[0]: (row[1] or "") for row in rows}
    except Exception:
        return {}


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
        created_at=row.created_at,
        expires_at=row.expires_at,
    )
