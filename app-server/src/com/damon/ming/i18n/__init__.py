# i18n/__init__.py
"""
服务端 i18n 模块 —— 最小入侵的国际化方案。

架构：
  t(key, **params)  ← facade（路由器/中间件唯一调用点）
       │
       ▼
  LocaleContext    ← contextvars，请求级 locale
       │
       ▼
  MessageResolver  ← 当前 LocalResolver(JSON)，未来 RemoteResolver(翻译中台)

用法：
  from i18n import t, I18nKey
  error_msg = t(I18nKey.UPLOAD_SIZE_EXCEEDED, max_mb="10")

启动时：
  from i18n import configure
  from i18n.resolver import LocalResolver
  configure(LocalResolver(locales_dir="i18n/locales"))
"""

import contextvars
from typing import Protocol

# 请求级 locale —— 中间件设置，t() 读取
_locale_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "locale", default="zh_CN"
)

# 全局 resolver —— AppInitializer 启动时注入
_resolver: "MessageResolver | None" = None


class MessageResolver(Protocol):
    """翻译解析器接口 —— 当前本地 JSON，未来替换为翻译中台客户端。"""

    def resolve(self, key: str, locale: str, **params) -> str: ...


def t(key: str, **params) -> str:
    """翻译 —— 唯一调用点。

    根据当前请求的 locale 解析 key → 本地化文案。
    未找到 key 时返回 key 本身（兜底，不会报错）。
    """
    if _resolver is None:
        # 未配置时直接返回 key（启动前/测试场景的降级）
        return key
    locale = _locale_var.get()
    return _resolver.resolve(key, locale, **params)


def set_locale(locale: str) -> None:
    """中间件设置当前请求的 locale。"""
    _locale_var.set(locale)


def get_locale() -> str:
    """获取当前请求的 locale。"""
    return _locale_var.get()


def configure(resolver: MessageResolver) -> None:
    """AppInitializer 启动时注入 resolver 实现。"""
    global _resolver
    _resolver = resolver
