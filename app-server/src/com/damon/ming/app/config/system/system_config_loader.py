# app/config/system/system_config_loader.py
"""
系统级配置加载器 —— 跨模块共享的路径和基础设置。

各模块不再自行硬编码路径，统一从 app.state.system_config 读取。
"""

import os
from dataclasses import dataclass
from pathlib import Path

from src.com.damon.ming.app.config._yaml import load_yaml


@dataclass(frozen=True)
class SystemConfig:
    """系统级配置（纯数据类）。所有参数由 YAML 显式声明，无内置默认值。"""

    knowledge_dir: str  # 知识库目录绝对路径


class SystemConfigLoader:
    """从 YAML 加载系统级配置，解析相对路径为绝对路径。

    Returns:
        SystemConfig: knowledge_dir 已解析为绝对路径。
    """

    def __init__(self):
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self) -> SystemConfig:
        raw = self._read_yaml()

        knowledge_dir = raw.get("knowledge_dir")
        if not knowledge_dir:
            raise ValueError(
                f"系统配置中 knowledge_dir 不能为空 | dir={self._config_dir}"
            )

        # 支持绝对路径（直接使用）或相对路径（基于 app-server/ 根目录解析）
        # __file__ = src/com/damon/ming/app/config/system/system_config_loader.py
        # parents[7] = app-server/
        if not os.path.isabs(knowledge_dir):
            project_root = Path(__file__).resolve().parents[7]
            knowledge_dir = str((project_root / knowledge_dir).resolve())

        return SystemConfig(knowledge_dir=knowledge_dir)

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)
