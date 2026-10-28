# app/config/system/system_config_loader.py
"""
系统级配置加载器 —— 跨模块共享的路径和基础设置。

各模块不再自行硬编码路径，统一从 app.state.system_config 读取。
"""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SystemConfig:
    """系统级配置（纯数据类）。所有参数由 YAML 显式声明，无内置默认值。"""

    knowledge_dir: str  # 知识库目录绝对路径


class SystemConfigLoader:
    """从 YAML 加载系统级配置，解析相对路径为绝对路径。

    Returns:
        SystemConfig: knowledge_dir 已解析为绝对路径。
    """

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = os.environ.get("SYSTEM_CONFIG_PATH", "")
        if not config_path:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "system-config.yaml")
        self._config_path = config_path

    def load(self) -> SystemConfig:
        raw = self._read_yaml()
        section = raw.get("system", {})
        if not section:
            raise ValueError(
                f"系统配置格式错误：缺少 'system' 根节点 | path={self._config_path}"
            )

        knowledge_dir = section.get("knowledge_dir")
        if not knowledge_dir:
            raise ValueError(
                f"系统配置中 knowledge_dir 不能为空 | path={self._config_path}"
            )

        # 支持绝对路径（直接使用）或相对路径（基于 app-server/ 根目录解析）
        # __file__ = src/com/damon/ming/app/config/system/system_config_loader.py
        # parents[7] = app-server/
        if not os.path.isabs(knowledge_dir):
            project_root = Path(__file__).resolve().parents[7]
            knowledge_dir = str((project_root / knowledge_dir).resolve())

        return SystemConfig(knowledge_dir=knowledge_dir)

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"系统配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if not raw_cfg or not isinstance(raw_cfg, dict):
            raise ValueError("系统配置文件格式错误：需要顶层键值对")
        return raw_cfg
