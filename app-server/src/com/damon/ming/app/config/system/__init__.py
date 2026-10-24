# app/config/system/__init__.py
"""系统级配置子模块 —— YAML 配置 + 加载器。"""

from src.com.damon.ming.app.config.system.system_config_loader import (
    SystemConfig,
    SystemConfigLoader,
)

__all__ = ["SystemConfig", "SystemConfigLoader"]
