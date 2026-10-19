# app-server/src/com/damon/ming/app/config/i18n/i18n_config_loader.py
"""
i18n 配置加载器 —— 从 YAML 读取 supported_locales / default_locale。
"""

import os

import yaml


class I18nConfig:
    """i18n 模块配置。"""

    __slots__ = ("default_locale", "supported_locales")

    def __init__(self, default_locale: str, supported_locales: list[str]):
        self.default_locale = default_locale
        self.supported_locales = supported_locales


class I18nConfigLoader:
    """从 YAML 文件加载 i18n 配置。"""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "i18n-config.yaml")
        self._config_path = config_path

    def load(self) -> I18nConfig:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if raw is None or "i18n" not in raw:
            raise ValueError("配置文件格式错误：缺少 'i18n' 根节点")
        section = raw["i18n"]
        return I18nConfig(
            default_locale=str(section.get("default_locale", "zh_CN")),
            supported_locales=list(section.get("supported_locales", ["zh_CN"])),
        )
