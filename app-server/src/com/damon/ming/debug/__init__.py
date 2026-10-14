# app-server/src/com/damon/ming/debug/__init__.py
"""
服务端 Debug 全局状态 —— 构建时注入 + 启动时冻结，运行时不可变。

优先级（从高到低）：
  1. build_info.py —— Docker/CI 构建时烘焙的值（生产镜像固化，运行时不可变）
  2. APP_ENV 环境变量 —— 本地开发时使用

设计：
  - build_info.py 存在 → 使用其 SERVER_BUILD_ENV 值，完全忽略 APP_ENV
  - build_info.py 不存在 → 回退到 APP_ENV 环境变量（本地开发默认 debug）
  - 值在模块首次加载时冻结，整个进程生命周期不变

用法：
  from src.com.damon.ming.debug import is_debug, is_trust_client_env, get_runtime_config

  if is_debug():
      logger.info("当前为 debug 模式")
"""

import os
from typing import Any

from src.com.damon.ming.log import pin

logger = pin("ming.debug")

# ---------------------------------------------------------------------------
# 核心环境标志 —— 构建时决定"是否可切换"，启动时冻结最终值，运行时不可变
#
# build_info.py 优先级（从高到低）：
#   1. SERVER_BUILD_ENV = 0 → 生产构建：锁定 release，忽略 APP_ENV，不可切换
#   2. SERVER_BUILD_ENV = 1 → 开发/预发构建：默认 debug，APP_ENV 可覆盖
#   3. 不存在 build_info.py  → 本地开发：默认 debug，APP_ENV 可覆盖
#
# 无论哪种情况，_IS_DEBUG 在模块首次加载后即冻结，运行时不可变。
# ---------------------------------------------------------------------------


def _resolve_is_debug() -> bool:
    """解析最终的 is_debug 值。"""
    _build_info_path = os.path.join(os.path.dirname(__file__), "build_info.py")
    if os.path.exists(_build_info_path):
        import importlib.util

        spec = importlib.util.spec_from_file_location("build_info", _build_info_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            build_env = getattr(module, "SERVER_BUILD_ENV", None)

            if str(build_env) == "0":
                # 生产构建：锁定 release，完全忽略 APP_ENV
                logger.info("使用环境标志（来源: SERVER_BUILD_ENV=0 → 锁定 release，运行时不可变）")
                return False

            # SERVER_BUILD_ENV = 1 → 可切换模式，读取 APP_ENV（默认 debug）
            env = os.environ.get("APP_ENV", "debug").lower()
            logger.info("使用环境标志（来源: SERVER_BUILD_ENV=1 + APP_ENV=%s）", env)
            return env == "debug"

    # 本地开发：读取 APP_ENV（默认 debug）
    env = os.environ.get("APP_ENV", "debug").lower()
    logger.info("使用环境标志（来源: APP_ENV=%s）", env)
    return env == "debug"


_IS_DEBUG: bool = _resolve_is_debug()


def is_debug() -> bool:
    """当前是否为 debug 环境（构建时/启动时冻结，运行时不可变）。"""
    return _IS_DEBUG


def get_env() -> str:
    """返回当前环境字符串：'debug' 或 'release'。"""
    return "debug" if _IS_DEBUG else "release"


# ---------------------------------------------------------------------------
# 运行时调试开关（仅 debug 环境可写，release 环境为只读）
# ---------------------------------------------------------------------------


class RuntimeConfig:
    """
    运行时调试配置 —— 仅 debug 环境允许修改。

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
        if not _IS_DEBUG:
            return default
        return self._debug_overrides.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置运行时开关（仅 debug 环境允许修改）。"""
        if not _IS_DEBUG:
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
    是否信任客户端 X-Client-Env 头（0 = debug, 1 = release）。
    debug 默认 True（方便联调），release 始终 False。
    """
    if not _IS_DEBUG:
        return False
    return _runtime_config.get("trust_client_env", True)


def is_skip_encryption() -> bool:
    """是否跳过加密（debug 专用，release 始终 False）。"""
    if not _IS_DEBUG:
        return False
    return _runtime_config.get("skip_encryption", False)


def is_skip_auth() -> bool:
    """是否跳过认证（debug 专用，release 始终 False）。"""
    if not _IS_DEBUG:
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
