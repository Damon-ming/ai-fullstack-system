# app-server/src/com/damon/ming/middleware/header_constants.py
"""
HTTP 请求头常量 —— 中间件层协议头统一管理。

所有 X-* 自定义头名称在此收拢，避免散落在中间件各处。
"""

# 加密协议头
ENCRYPT_ENABLED = "x-encrypt-enabled"
ENCRYPT_VERSION = "x-encrypt-version"

# 签名协议头
SIGNATURE_VERSION = "x-signature-version"

# 系统版本头
SYSTEM_VERSION = "x-system-version"

# 环境头
CLIENT_ENV = "x-client-env"
