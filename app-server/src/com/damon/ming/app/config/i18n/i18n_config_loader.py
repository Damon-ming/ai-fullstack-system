# app-server/src/com/damon/ming/app/config/i18n/i18n_config_loader.py
"""
i18n 配置加载器 —— 从 YAML 读取 supported_locales / default_locale。

配置来源：本目录下唯一的 YAML 文件。
"""

import os

from src.com.damon.ming.app.config._yaml import load_yaml


class I18nConfig:
    """i18n 模块配置。"""

    __slots__ = ("default_locale", "supported_locales")

    def __init__(self, default_locale: str, supported_locales: list[str]):
        self.default_locale = default_locale
        self.supported_locales = supported_locales


class I18nConfigLoader:
    """从 YAML 文件加载 i18n 配置。"""

    KEYS = ("default_locale", "supported_locales")

    def __init__(self):
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self) -> I18nConfig:
        """加载 i18n 配置。必填字段缺失直接抛异常，不做静默降级。"""
        raw = load_yaml(self._config_dir)

        missing = [
            key
            for key in self.KEYS
            if raw.get(key) is None or raw.get(key) == "" or raw.get(key) == []
        ]
        if missing:
            raise ValueError(f"i18n 配置缺少必填字段：{', '.join(missing)}")

        return I18nConfig(
            default_locale=str(raw["default_locale"]),
            supported_locales=[str(locale) for locale in raw["supported_locales"]],
        )
