# app-server/src/com/damon/ming/utils/yaml_loader.py
"""读取配置目录中唯一的 YAML 文件，或显式指定的 YAML 文件。"""

from pathlib import Path
from typing import Any

import yaml


def resolve_yaml_path(location: str | Path) -> Path:
    """解析配置路径；传目录时要求目录下恰好有一个 YAML 文件。"""
    path = Path(location).resolve()
    if path.is_file():
        return path
    if path.suffix.lower() in {".yaml", ".yml"}:
        raise FileNotFoundError(f"配置文件不存在: {path}")
    if not path.is_dir():
        raise FileNotFoundError(f"配置目录不存在: {path}")

    matches = sorted(
        item
        for item in path.iterdir()
        if item.is_file() and item.suffix.lower() in {".yaml", ".yml"}
    )
    if not matches:
        raise FileNotFoundError(f"配置目录下没有 YAML 文件: {path}")
    if len(matches) > 1:
        names = ", ".join(item.name for item in matches)
        raise ValueError(f"配置目录下存在多个 YAML 文件: {names} | dir={path}")
    return matches[0]


def load_yaml(location: str | Path, *, allow_empty: bool = False) -> dict[str, Any]:
    """读取 YAML 字典；location 可以是配置目录或显式文件路径。"""
    path = resolve_yaml_path(location)
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    if allow_empty and (raw is None or raw == {}):
        return {}
    if not raw or not isinstance(raw, dict):
        raise ValueError(f"配置文件格式错误：需要顶层键值对 | path={path}")
    return raw
