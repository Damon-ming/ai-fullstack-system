# app-server/src/com/damon/ming/app/config/_yaml.py
"""
YAML 配置读取工具。

约定：每个配置子目录（db / encryption / i18n / inference / system / thread / upload）
下恰好有一个 .yaml / .yml 文件。调用方把配置目录传给 load_yaml()，直接拿到解析后的字典。
"""

import glob
import os
from typing import Any

import yaml


def load_yaml(directory: str) -> dict[str, Any]:
    """读取目录下唯一的 YAML 文件并返回解析结果。

    Raises:
        FileNotFoundError: 目录下没有 YAML 文件。
        ValueError: 目录下有多个 YAML 文件，或文件为空 / 顶层不是键值对。
    """
    matches = sorted(
        glob.glob(os.path.join(directory, "*.yaml"))
        + glob.glob(os.path.join(directory, "*.yml"))
    )
    if not matches:
        raise FileNotFoundError(f"配置目录下没有 YAML 文件: {directory}")
    if len(matches) > 1:
        names = ", ".join(os.path.basename(m) for m in matches)
        raise ValueError(f"配置目录下存在多个 YAML 文件: {names} | dir={directory}")

    path = matches[0]
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not raw or not isinstance(raw, dict):
        raise ValueError(f"配置文件格式错误：需要顶层键值对 | path={path}")
    return raw
