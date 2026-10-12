# app-server/src/com/damon/ming/router/account/token_store.py
"""
Token 存储层 —— 用户身份 + 设备 + UA 管理。

职责：
  - 维护 phone → token 映射（用户身份层，一个手机号一个 token）
  - 维护 device_id → phone 映射（设备层，一个用户可有多台设备）
  - 维护 device_id → UA 哈希（签发时的 UA 指纹，用于校验）
  - 线程安全的增删查操作

设计：
  - 当前用内存 dict 存储（TODO: 后期迁移到 DB）
  - 纯数据管理，不涉及 HTTP 逻辑
  - 可被 account_router、auth_middleware 共同依赖

关联关系：
  phone ──1:1── token      （一个用户一个身份令牌）
  phone ──1:N── device_id  （一个用户多台设备）
  device_id ──1:1── ua_hash（每台设备签发时的 UA 指纹）
"""

import threading
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class DeviceRecord:
    """一台已注册设备的信息。"""

    device_id: str
    phone: str
    ua_hash: str  # 签发时的完整 UA 哈希
    token: str  # 绑定的 token（同 phone 的所有设备共享同一个 token）


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------

_lock = threading.RLock()

# phone → token（用户身份层）
_phone_token_map: dict[str, str] = {}

# token → phone（反向查询）
_token_phone_map: dict[str, str] = {}

# device_id → DeviceRecord（设备层）
_devices: dict[str, DeviceRecord] = {}


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
    """绑定 phone → token 映射（幂等，同 phone 覆盖旧 token）。"""
    with _lock:
        # 如果该 phone 已有旧 token，清理旧反向映射
        old_token = _phone_token_map.get(phone)
        if old_token and old_token != token:
            _token_phone_map.pop(old_token, None)
            # 清理该设备下旧 token 关联的所有设备记录
            for dev_id, rec in list(_devices.items()):
                if rec.token == old_token:
                    del _devices[dev_id]

        _phone_token_map[phone] = token
        _token_phone_map[token] = phone


# ---------------------------------------------------------------------------
# 设备（device_id → DeviceRecord）
# ---------------------------------------------------------------------------


def get_device(device_id: str) -> DeviceRecord | None:
    """查询设备记录。"""
    with _lock:
        return _devices.get(device_id)


def get_devices_by_phone(phone: str) -> list[DeviceRecord]:
    """查询某用户的所有设备。"""
    with _lock:
        return [rec for rec in _devices.values() if rec.phone == phone]


def register_device(device_id: str, phone: str, ua_hash: str, token: str) -> None:
    """
    注册一台设备。

    如果 device_id 已存在且属于同一 phone，更新 UA hash（设备信息可能变化）。
    如果 device_id 已存在但属于不同 phone，拒绝（设备被另一用户使用）。
    """
    with _lock:
        existing = _devices.get(device_id)
        if existing and existing.phone != phone:
            raise ValueError(f"设备 {device_id[:12]}... 已被另一用户注册，不可重复绑定")
        _devices[device_id] = DeviceRecord(
            device_id=device_id,
            phone=phone,
            ua_hash=ua_hash,
            token=token,
        )


def remove_device(device_id: str) -> None:
    """删除设备记录。"""
    with _lock:
        _devices.pop(device_id, None)


# ---------------------------------------------------------------------------
# 联合查询
# ---------------------------------------------------------------------------


def get_ua_hash_by_token(token: str) -> str | None:
    """
    获取某 token 对应的 UA hash。

    返回该用户最近一次注册设备的 UA hash。
    用于中间件校验当前请求 UA 是否与签发时一致。
    """
    with _lock:
        phone = _token_phone_map.get(token)
        if not phone:
            return None
        devices = [rec for rec in _devices.values() if rec.phone == phone]
        if not devices:
            return None
        # 返回最近注册的设备 UA（列表最后一个）
        return devices[-1].ua_hash


# ---------------------------------------------------------------------------
# 调试 / 管理
# ---------------------------------------------------------------------------


def get_all_devices() -> list[DeviceRecord]:
    """获取所有设备记录副本（调试用）。"""
    with _lock:
        return list(_devices.values())


def get_stats() -> dict:
    """获取统计信息。"""
    with _lock:
        return {
            "users": len(_phone_token_map),
            "devices": len(_devices),
        }
