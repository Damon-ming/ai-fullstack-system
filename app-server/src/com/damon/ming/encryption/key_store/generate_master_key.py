# app-server/src/com/damon/ming/encryption/generate_master_key.py
"""生成 MASTER_KEY 并注入环境变量（仅开发环境使用）。

TODO: 生产环境必须通过运维密钥管理系统（Vault/K8s Secret/云密钥服务）注入，
      严禁将密钥生成逻辑或硬编码密钥提交到代码仓库。
      上线前应删除此文件或限制为仅本地开发脚本。
"""

import secrets


def generate_master_key(length: int = 36) -> str:
    """生成安全的随机主密钥。"""
    return secrets.token_urlsafe(length)
