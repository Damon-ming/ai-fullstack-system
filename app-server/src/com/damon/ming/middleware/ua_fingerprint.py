# app-server/src/com/damon/ming/middleware/ua_fingerprint.py
"""
UA 指纹工具 —— 从浏览器环境摘要计算设备唯一标识。

职责：
  - 解析 X-Client-UA header
  - 计算设备指纹（device_id）
  - 比对两个 UA 摘要是否指向同一设备

设计：
  - 纯工具模块，不含业务逻辑、不依赖 store / DB
  - device_id = SHA-256(UA 关键字段)，同一浏览器大概率相同
  - UA 比对允许部分字段变化（如版本号升级），不要求完全一致
"""

import hashlib
import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class UAProfile(NamedTuple):
    """解析后的浏览器环境摘要。"""

    raw_ua: str
    lang: str
    platform: str
    screen: str
    tz: str


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

_PIPE_SPLIT = re.compile(r"\|")


def parse_ua_header(header_value: str) -> UAProfile:
    """
    解析 X-Client-UA header 字符串。

    格式: "<UA>|<lang>|<platform>|<screenW>x<screenH>|<timezone>"
    示例: "Mozilla/5.0 ... Chrome/131|zh-CN|Win32|1920x1080|Asia/Shanghai"

    解析失败时返回全空 UAProfile，调用方决定如何处理。
    """
    parts = _PIPE_SPLIT.split(header_value or "")

    return UAProfile(
        raw_ua=parts[0].strip() if len(parts) > 0 else "",
        lang=parts[1].strip() if len(parts) > 1 else "",
        platform=parts[2].strip() if len(parts) > 2 else "",
        screen=parts[3].strip() if len(parts) > 3 else "",
        tz=parts[4].strip() if len(parts) > 4 else "",
    )


# ---------------------------------------------------------------------------
# 设备指纹计算
# ---------------------------------------------------------------------------

# 用于指纹计算的 UA 关键字段（去掉版本号等易变部分）
_BROWSER_CORE_RE = re.compile(
    r"(?P<browser>Chrome|Firefox|Safari|Edg|Edge|Opera|OPR|MSIE|Trident)"
    r"/\d+",
)


def _normalize_ua(raw_ua: str) -> str:
    """提取 UA 中的浏览器核心标识，去掉具体版本号。

    例如 "Chrome/131.0.0.0" → "Chrome"，减少版本升级带来的指纹漂移。
    """
    m = _BROWSER_CORE_RE.search(raw_ua)
    return m.group("browser") if m else raw_ua[:80]


def compute_device_id(profile: UAProfile) -> str:
    """
    根据浏览器环境摘要计算设备唯一标识。

    取 UA 核心字段 + platform + screen + lang 组合哈希，
    同一浏览器在同一台机器上大概率产出相同指纹。

    返回 16 进制字符串（SHA-256 前 16 字节）。
    """
    components = [
        _normalize_ua(profile.raw_ua),
        profile.platform,
        profile.screen,
        profile.lang,
    ]
    fingerprint_input = "||".join(components)
    return hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()[:32]


def compute_ua_hash(profile: UAProfile) -> str:
    """
    计算完整 UA 摘要的哈希（用于精确比对）。

    与 compute_device_id 不同，这个包含完整原始 UA，
    任何字段变化都会导致哈希不同，用于安全校验。
    """
    fingerprint_input = f"{profile.raw_ua}|{profile.lang}|{profile.platform}|{profile.screen}|{profile.tz}"
    return hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 比对
# ---------------------------------------------------------------------------


def is_same_device(
    issued_profile: UAProfile,
    current_profile: UAProfile,
) -> bool:
    """
    判断两次 UA 是否指向同一设备。

    策略：UA 核心指纹 + platform + screen + lang 完全匹配即视为同一设备。
    timezone 不参与（用户跨时区旅行时不应掉登录）。
    """
    return compute_device_id(issued_profile) == compute_device_id(current_profile)


def has_ua_changed_significantly(
    old_hash: str,
    profile: UAProfile,
) -> bool:
    """判断 UA 是否发生过显著变化（完整哈希不一致）。"""
    return old_hash != compute_ua_hash(profile)
