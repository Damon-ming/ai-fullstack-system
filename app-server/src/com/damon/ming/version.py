# app-server/src/com/damon/ming/version.py
"""
系统版本号 —— 后端系统整体版本标识。

用于：
  - 前端通过 X-System-Version header 上报自身版本，服务端可据此做兼容或统计
  - 健康检查 / 监控接口返回当前后端版本
  - 日志标记，方便排查版本相关的问题
"""

SYSTEM_VERSION = "1.0.0"
