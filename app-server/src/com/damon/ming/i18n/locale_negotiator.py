# app-server/src/com/damon/ming/i18n/locale_negotiator.py
"""
Locale 协商 —— 解析 X-Language 头值，匹配最佳 locale。

X-Language 头由上层（中间件）解析后以字符串传入，本模块不感知 HTTP 请求对象。
配置由 app_initializer 从 YAML 注入（configure()），全部走配置，无硬编码默认值。

支持格式：
  X-Language: en-US,en;q=0.9,zh-CN;q=0.8
  X-Language: zh-CN
  X-Language: en
"""

from . import set_locale

# 由 configure() 注入，未配置时为 None
DEFAULT_LOCALE: str | None = None
SUPPORTED_LOCALES: set[str] | None = None


def configure(default_locale: str, supported_locales: list[str]) -> None:
    """注入 YAML 配置。由 app_initializer 启动时调用。"""
    global DEFAULT_LOCALE, SUPPORTED_LOCALES
    DEFAULT_LOCALE = default_locale
    SUPPORTED_LOCALES = set(supported_locales)


def get_default_locale() -> str:
    """返回 YAML 配置的默认 locale（回退口径）。

    与 negotiate_locale 共用同一配置来源，供需要回退默认 locale 的调用方使用。
    """
    if DEFAULT_LOCALE is None:
        raise RuntimeError("locale_negotiator 未配置，请先调用 configure()")
    return DEFAULT_LOCALE


def negotiate_locale(header_value: str) -> str:
    """解析 X-Language 头 → 最佳匹配 locale。

    匹配优先级：
      1. 精确匹配 (en_US → en_US)
      2. 语言前缀匹配 (en → en_US)
      3. 默认 locale（来自 YAML 配置）
    """
    if DEFAULT_LOCALE is None or SUPPORTED_LOCALES is None:
        raise RuntimeError("locale_negotiator 未配置，请先调用 configure()")

    if not header_value:
        return DEFAULT_LOCALE

    # 解析 Accept-Language 风格的权重列表
    tags = _parse_language_header(header_value)

    for locale_str, _ in tags:
        normalized = locale_str.replace("-", "_")

        # 精确匹配
        if normalized in SUPPORTED_LOCALES:
            return normalized

        # 大小写不敏感的精确匹配
        for supported in SUPPORTED_LOCALES:
            if supported.lower() == normalized.lower():
                return supported

    # 第二轮：语言前缀匹配
    for locale_str, _ in tags:
        lang_prefix = locale_str.replace("-", "_").split("_")[0].lower()
        for supported in SUPPORTED_LOCALES:
            if supported.lower().startswith(lang_prefix):
                return supported

    return DEFAULT_LOCALE


def apply_locale(header_value: str) -> str:
    """解析 X-Language 头值 → 最佳 locale，并设置到当前上下文。返回解析结果。

    参数：
      header_value: X-Language 头的原始值，由上层 HTTP 层解析后传入。
    """
    locale = negotiate_locale(header_value)
    set_locale(locale)
    return locale


def _parse_language_header(header_value: str) -> list[tuple[str, float]]:
    """解析 X-Language 头为 [(locale, quality), ...] 列表，按 quality 降序。"""
    tags: list[tuple[str, float]] = []
    for part in header_value.split(","):
        part = part.strip()
        if not part:
            continue
        if ";q=" in part:
            locale_str, q_str = part.split(";q=", 1)
            try:
                quality = float(q_str)
            except ValueError:
                quality = 1.0
        else:
            locale_str = part
            quality = 1.0
        tags.append((locale_str.strip(), quality))

    # 按 quality 降序排序
    tags.sort(key=lambda x: x[1], reverse=True)
    return tags
