# app-server/src/com/damon/ming/router/account/token_store.py
"""
Token 存储层 —— 纯数据管理，不涉及 HTTP 逻辑。

职责：
  - 维护 token 白名单（内存 set）
  - 维护 device_id → token 映射（同设备复用 token）
  - 线程安全的增删查操作

设计：
  - 不依赖任何中间件或路由模块
  - 可被 account_router、auth_middleware 共同依赖
"""

import threading

_lock = threading.Lock()

# token 白名单
_token_whitelist: set[str] = set()

# device_id → token 映射（同设备复用）
_device_token_map: dict[str, str] = {}


def add_token(token: str, device_id: str | None = None) -> None:
    """注册 token，可选绑定 device_id。"""
    with _lock:
        _token_whitelist.add(token)
        if device_id:
            _device_token_map[device_id] = token


def remove_token(token: str) -> None:
    """移除 token 及其 device_id 映射。"""
    with _lock:
        _token_whitelist.discard(token)
        for did, tok in list(_device_token_map.items()):
            if tok == token:
                del _device_token_map[did]


def get_token_by_device_id(device_id: str) -> str | None:
    """根据 device_id 查询已签发的 token。"""
    with _lock:
        return _device_token_map.get(device_id)


def is_token_valid(token: str) -> bool:
    """检查 token 是否在白名单中。"""
    with _lock:
        return token in _token_whitelist


def get_whitelist() -> set[str]:
    """获取白名单副本（供中间件使用）。"""
    with _lock:
        return _token_whitelist.copy()
