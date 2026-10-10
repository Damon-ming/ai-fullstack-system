# app-server/src/com/damon/ming/encryption/generate_master_key.py
"""生成 MASTER_KEY 并注入环境变量（仅开发环境使用）。

TODO: 生产环境必须通过运维密钥管理系统（Vault/K8s Secret/云密钥服务）注入，
      严禁将密钥生成逻辑或硬编码密钥提交到代码仓库。
      上线前应删除此文件或限制为仅本地开发脚本。
"""

import os
import secrets


def generate_master_key(length: int = 36) -> str:
    """生成安全的随机主密钥。"""
    return secrets.token_urlsafe(length)


def inject_to_env(key: str | None = None) -> str:
    """将主密钥注入进程环境变量 MASTER_KEY。

    返回使用的密钥值，便于调用方确认。
    """
    if key is None:
        key = generate_master_key()
    os.environ["MASTER_KEY"] = key
    return key
