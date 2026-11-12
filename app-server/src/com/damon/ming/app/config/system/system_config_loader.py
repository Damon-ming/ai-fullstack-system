# app/config/system/system_config_loader.py
"""
系统级配置加载器 —— 跨模块共享的路径和基础设置。

各模块不再自行硬编码路径，统一从 app.state.config.system_config 读取。
"""

import os
from dataclasses import dataclass
from pathlib import Path

from src.com.damon.ming.app.config._yaml import load_yaml


@dataclass(frozen=True)
class SystemConfig:
    """系统级配置（纯数据类）。所有参数由 YAML 显式声明，无内置默认值。"""

    knowledge_dir: str  # 知识库目录绝对路径
    whitelist: tuple[str, ...]  # 加密豁免路径前缀（明文放行）


# 密钥交换端点必须在白名单内：它自身没有加密会话可用，
# 漏配会让所有客户端无法建立加密会话（release 下直接不可用）。
_REQUIRED_WHITELIST_PREFIX = "/api/encryption"


class SystemConfigLoader:
    """从 YAML 加载系统级配置，解析相对路径为绝对路径。

    Returns:
        SystemConfig: knowledge_dir 已解析为绝对路径，whitelist 已校验。
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

        whitelist = self._parse_whitelist(raw.get("whitelist"))

        return SystemConfig(knowledge_dir=knowledge_dir, whitelist=whitelist)

    def _parse_whitelist(self, raw: object) -> tuple[str, ...]:
        """解析加密豁免白名单（缺失/为空直接抛异常，不静默降级）。

        白名单决定哪些请求可以明文通过，是安全策略的一部分：
        空列表会让所有端点强制加密，漏配密钥交换端点会让系统不可用。
        """
        if raw is None:
            raise ValueError("系统配置缺少必填字段：whitelist")
        if not isinstance(raw, (list, tuple)) or len(raw) == 0:
            raise ValueError("系统配置中 whitelist 必须是非空列表")

        whitelist = tuple(str(item) for item in raw)
        invalid = [item for item in whitelist if not item.startswith("/")]
        if invalid:
            raise ValueError(
                f"系统配置中 whitelist 条目必须以 / 开头：{', '.join(invalid)}"
            )

        if not any(
            _REQUIRED_WHITELIST_PREFIX.startswith(prefix)
            for prefix in whitelist
        ):
            raise ValueError(
                f"系统配置中 whitelist 缺少必要端点：{_REQUIRED_WHITELIST_PREFIX}"
                f"（密钥交换无法完成）"
            )

        return whitelist

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)
