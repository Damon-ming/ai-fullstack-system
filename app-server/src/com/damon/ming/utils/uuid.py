"""UUID 生成工具。"""

from uuid import uuid4


def generate_uuid() -> str:
    """生成标准格式的 UUID 字符串。"""
    return str(uuid4())


def generate_uuid_hex() -> str:
    """生成不含连字符的 UUID 字符串。"""
    return uuid4().hex
