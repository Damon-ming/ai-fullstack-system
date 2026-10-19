# i18n/resolver.py
"""
本地翻译解析器 —— 从 JSON 文件加载文案，支持参数插值。

回退链：
  精确 locale (en_US) → 语言前缀 (en) → 默认 locale (zh_CN) → key 本身
"""

import json
import os
import threading


class LocalResolver:
    """本地 JSON 文件翻译解析器。"""

    def __init__(
        self,
        locales_dir: str,
        default_locale: str,
        supported_locales: set[str],
    ):
        self._locales_dir = locales_dir
        self._default_locale = default_locale
        self._supported_locales = supported_locales
        self._cache: dict[str, dict[str, str]] = {}  # locale → {key: template}
        self._lock = threading.Lock()
        self._loaded = False

    def resolve(self, key: str, locale: str, **params) -> str:
        """解析 key → 本地化文案。"""
        self._ensure_loaded()

        # 回退链查找
        template = self._find_template(key, locale)

        if template is None:
            return key  # 兜底：返回 key 本身

        # 参数插值
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            # 参数不匹配时返回原始模板（不报错，优雅降级）
            return template

    # ── 私有 ────────────────────────────────────────────────

    def _find_template(self, key: str, locale: str) -> str | None:
        """按回退链查找模板。"""
        # 1. 精确匹配
        template = self._get_locale_dict(locale).get(key)
        if template is not None:
            return template

        # 2. 语言前缀匹配 (en_US → en)
        lang_prefix = locale.split("_")[0]
        for supported in self._supported_locales:
            if supported.startswith(lang_prefix):
                template = self._get_locale_dict(supported).get(key)
                if template is not None:
                    return template

        # 3. 默认 locale 回退
        if locale != self._default_locale:
            template = self._get_locale_dict(self._default_locale).get(key)
            if template is not None:
                return template

        return None

    def _get_locale_dict(self, locale: str) -> dict[str, str]:
        """获取 locale 文案字典（懒加载 + 缓存）。"""
        if locale not in self._cache:
            self._cache[locale] = self._load_locale_file(locale)
        return self._cache.get(locale, {})

    def _load_locale_file(self, locale: str) -> dict[str, str]:
        """从 JSON 文件加载 locale 文案。"""
        path = os.path.join(self._locales_dir, f"{locale}.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _ensure_loaded(self) -> None:
        """启动时预加载所有支持的 locale。"""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            for locale in self._supported_locales:
                self._cache[locale] = self._load_locale_file(locale)
            self._loaded = True
