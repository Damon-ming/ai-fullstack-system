# app-server/src/com/damon/ming/encryption/cipher_suite.py
"""
加密套件 — 声明不同场景用什么算法组合。

不同场景的安全需求不同，算法选择也不同：
  - NETWORK_HYBRID:       RSA-OAEP + AES-256-GCM  （需要密钥交换，用于 HTTP 请求）
  - DATABASE_AES_GCM:    AES-256-GCM              （纯对称，服务端持有密钥，用于 DB 字段）
  - DATABASE_DETERMINISTIC: AES-256-GCM + 派生 nonce  （相同明文→相同密文，支持等值查询）
  - BLIND_INDEX:         BLAKE2b-HMAC              （只生成索引，不解密，用于加密字段查询）

设计原则：
  - 上层声明意图（CipherSuite），引擎内部决定用什么算法
  - 加新场景时上层调用代码不用动
  - 纯枚举 + 分发，零外部依赖
"""

from enum import Enum


class CipherSuite(str, Enum):
    """按场景分的加密套件。"""

    # 网络请求：RSA 密钥交换 + AES-GCM 对称加密
    NETWORK_HYBRID = "rsa_oaep+aes256gcm"

    # 数据库字段：AES-GCM + 随机 nonce（每次结果不同，不支持查询）
    DATABASE_AES_GCM = "aes256gcm"

    # 数据库字段（确定性）：AES-GCM + 从明文派生的 nonce（支持等值查询）
    DATABASE_DETERMINISTIC = "aes256gcm_det"

    # 盲索引：BLAKE2b-HMAC，仅生成查询用的索引值，不解密
    BLIND_INDEX = "blake2b_hmac"
