# app-server/src/com/damon/ming/debug/__init__.py
"""
服务端 Debug 全局状态

职责：
  - 集中管理 "当前是否为 debug 环境" 这一事实
  - 提供 is_debug() 函数供任意模块查询，避免各自读取 os.environ
  - 提供运行时调试开关（如：强制信任客户端环境头、跳过认证）

用法：
  from com.damon.ming.debug import is_debug, is_trust_client_env, get_runtime_config

  if is_debug():
      logger.info("当前为 debug 模式")
"""

import os
from typing import Any

from src.com.damon.ming.log import pin

logger = pin("ming.debug")

# ---------------------------------------------------------------------------
# 核心环境标志
# ---------------------------------------------------------------------------


def is_debug() -> bool:
    """当前是否为 debug 环境（读取 APP_ENV 环境变量，默认 release"""
    return os.environ.get("APP_ENV", "release").lower() == "debug"


def get_env() -> str:
    """返回当前环境字符串：'debug' 或 'release'。"""
    return "debug" if is_debug() else "release"


# ---------------------------------------------------------------------------
# 运行时调试开关（debug 环境专用）
# ---------------------------------------------------------------------------


class RuntimeConfig:
    """
    运行时调试配置 —— 仅 debug 环境有效。

    用途：
      - 在 debug 环境模拟 release 行为（强制加密、认证）
      - 信任客户端 X-Client-Env 头（联调测试）
      - 跳过特定中间件（如：跳过认证以测试无 token 场景）

    release 环境始终返回默认值（最安全配置），运行时修改无效。
    """

    def __init__(self) -> None:
        self._debug_overrides: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """获取运行时开关值（仅 debug 环境生效）。"""
        if not is_debug():
            return default
        return self._debug_overrides.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置运行时开关（仅 debug 环境允许修改）。"""
        if not is_debug():
            logger.warning("release 环境不允许修改运行时开关: %s", key)
            return
        self._debug_overrides[key] = value
        logger.info("调试开关已设置: %s = %s", key, value)

    def reset(self) -> None:
        """重置所有运行时开关。"""
        self._debug_overrides.clear()
        logger.info("所有调试开关已重置")


# 单例实例
_runtime_config = RuntimeConfig()


def get_runtime_config() -> RuntimeConfig:
    """获取全局 RuntimeConfig 单例。"""
    return _runtime_config


# ---------------------------------------------------------------------------
# 便捷函数（业务层常用）
# ---------------------------------------------------------------------------


def is_trust_client_env() -> bool:
    """
    是否信任客户端 X-Client-Env 头。
    debug 默认 True（方便联调），release 始终 False。
    """
    if not is_debug():
        return False
    return _runtime_config.get("trust_client_env", True)


def is_skip_encryption() -> bool:
    """是否跳过加密（debug 专用，release 始终 False）。"""
    if not is_debug():
        return False
    return _runtime_config.get("skip_encryption", False)


def is_skip_auth() -> bool:
    """是否跳过认证（debug 专用，release 始终 False）。"""
    if not is_debug():
        return False
    return _runtime_config.get("skip_auth", False)


# ---------------------------------------------------------------------------
# 启动日志
# ---------------------------------------------------------------------------

logger.info(
    "Debug 模块初始化完成 | env=%s | trust_client_env=%s",
    get_env(),
    is_trust_client_env(),
)
