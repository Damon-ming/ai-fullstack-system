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

设计：
  - 当前用内存 dict 存储（TODO: 后期迁移到 DB）
  - 纯数据管理，不涉及 HTTP 逻辑
  - 可被 account_router、auth_middleware、encryption_router 共同依赖
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

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
    ua_hash: str  # 注册时的完整 UA 哈希
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SessionRecord:
    """一个会话实例（token + device_id 的唯一组合）。"""

    session_id: str
    token: str
    device_id: str
    ua_hash: str  # 签发时的 UA 哈希
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + SESSION_TTL)


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------

_lock = threading.RLock()

# phone → token（用户身份层）
_phone_token_map: dict[str, str] = {}

# token → phone（反向查询）
_token_phone_map: dict[str, str] = {}

# device_id → DeviceRecord（设备层，独立注册）
_devices: dict[str, DeviceRecord] = {}

# session_id → SessionRecord（会话层）
_sessions: dict[str, SessionRecord] = {}

# (token, device_id) → session_id（快速查找活跃会话）
_session_lookup: dict[tuple[str, str], str] = {}


# ---------------------------------------------------------------------------
# 用户（phone → token）
# ---------------------------------------------------------------------------


def get_token_by_phone(phone: str) -> str | None:
    """根据手机号查询已签发的 token。"""
    with _lock:
        return _phone_token_map.get(phone)


def get_phone_by_token(token: str) -> str | None:
    """根据 token 查询对应的手机号。"""
    with _lock:
        return _token_phone_map.get(token)


def is_token_valid(token: str) -> bool:
    """检查 token 是否存在。"""
    with _lock:
        return token in _token_phone_map


def bind_token(phone: str, token: str) -> None:
    """
    绑定 phone → token 映射（幂等，同 phone 覆盖旧 token）。

    注意：不清理设备和会话。设备独立存在，会话通过独立机制管理。
    """
    with _lock:
        old_token = _phone_token_map.get(phone)
        if old_token and old_token != token:
            _token_phone_map.pop(old_token, None)

        _phone_token_map[phone] = token
        _token_phone_map[token] = phone


# ---------------------------------------------------------------------------
# 设备（device_id → DeviceRecord）
# ---------------------------------------------------------------------------


def register_device(device_id: str, ua_hash: str) -> None:
    """
    注册一台设备。设备身份独立存在，不归属任何用户。

    如果 device_id 已存在，更新 UA hash（设备信息可能变化）。
    不再检查 phone 归属——同一个设备可以服务多个用户。
    """
    with _lock:
        _devices[device_id] = DeviceRecord(
            device_id=device_id,
            ua_hash=ua_hash,
        )


def get_device(device_id: str) -> DeviceRecord | None:
    """查询设备记录。"""
    with _lock:
        return _devices.get(device_id)


def is_device_registered(device_id: str) -> bool:
    """检查设备是否已注册。"""
    with _lock:
        return device_id in _devices


def remove_device(device_id: str) -> None:
    """删除设备记录（同时清理该设备的所有会话）。"""
    with _lock:
        _devices.pop(device_id, None)
        for sid, rec in list(_sessions.items()):
            if rec.device_id == device_id:
                _session_lookup.pop((rec.token, rec.device_id), None)
                del _sessions[sid]


# ---------------------------------------------------------------------------
# 会话（session_id → SessionRecord）
# ---------------------------------------------------------------------------


def create_session(token: str, device_id: str, ua_hash: str) -> str:
    """
    为 (token, device_id) 创建一个新会话。

    同一组合的旧会话立即过期（确保每个 token+device 只有一条活跃会话）。
    返回新 session_id。
    """
    with _lock:
        # 立即过期该组合的旧会话
        key = (token, device_id)
        old_sid = _session_lookup.get(key)
        if old_sid and old_sid in _sessions:
            _sessions[old_sid].expires_at = datetime.utcnow()

        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        record = SessionRecord(
            session_id=session_id,
            token=token,
            device_id=device_id,
            ua_hash=ua_hash,
            created_at=now,
            expires_at=now + SESSION_TTL,
        )
        _sessions[session_id] = record
        _session_lookup[key] = session_id
        return session_id


def get_session(session_id: str) -> SessionRecord | None:
    """查询有效会话（未过期）。"""
    with _lock:
        rec = _sessions.get(session_id)
        if rec is None:
            return None
        if rec.expires_at <= datetime.utcnow():
            # 过期清理
            _session_lookup.pop((rec.token, rec.device_id), None)
            del _sessions[session_id]
            return None
        return rec


def get_active_session(token: str, device_id: str) -> SessionRecord | None:
    """查询某 (token, device_id) 的活跃会话。"""
    with _lock:
        sid = _session_lookup.get((token, device_id))
        if sid:
            return get_session(sid)  # 内部检查过期
        return None


def revoke_sessions_by_token(token: str) -> int:
    """注销某 token 的所有会话（用户退出所有设备）。返回注销数量。"""
    with _lock:
        count = 0
        for sid, rec in list(_sessions.items()):
            if rec.token == token:
                _session_lookup.pop((rec.token, rec.device_id), None)
                del _sessions[sid]
                count += 1
        return count


def revoke_sessions_by_device(device_id: str) -> int:
    """注销某设备的所有会话（设备被踢出所有用户）。返回注销数量。"""
    with _lock:
        count = 0
        for sid, rec in list(_sessions.items()):
            if rec.device_id == device_id:
                _session_lookup.pop((rec.token, rec.device_id), None)
                del _sessions[sid]
                count += 1
        return count


# ---------------------------------------------------------------------------
# 调试 / 管理
# ---------------------------------------------------------------------------


def get_all_devices() -> list[DeviceRecord]:
    """获取所有设备记录副本（调试用）。"""
    with _lock:
        return list(_devices.values())


def get_all_sessions() -> list[SessionRecord]:
    """获取所有有效会话副本（调试用）。"""
    with _lock:
        now = datetime.utcnow()
        return [rec for rec in _sessions.values() if rec.expires_at > now]


def get_stats() -> dict:
    """获取统计信息。"""
    with _lock:
        now = datetime.utcnow()
        return {
            "users": len(_phone_token_map),
            "devices": len(_devices),
            "sessions": sum(1 for s in _sessions.values() if s.expires_at > now),
        }
