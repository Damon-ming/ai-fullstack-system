# app-server/src/com/damon/ming/encryption/constants.py
"""
加密常量 —— 协议参数 + 安全策略阈值。

这些值**不进 YAML 配置**：它们不是可调优的业务参数，而是协议 / 安全策略的组成部分。
密钥长度 / nonce 长度同时决定密文的二进制格式，改动必须全链路同步，
并且必须考虑历史密文的解密兼容性（通常意味着协议版本升级 + 数据迁移）。

依赖：无（纯常量，可被 encryption 下任意模块引用）。
"""

# ── AES-256-GCM ──────────────────────────────────────────────────────────
# 密钥长度同时决定 KEK 的长度（KEK 本身就是一把 AES-256 密钥）
AES_KEY_SIZE = 32  # 字节（256 bit）

# GCM 推荐 96 bit；同时是密文二进制格式的组成部分，改动会让历史密文解不开
AES_NONCE_SIZE = 12  # 字节

# 允许接收的 AES 密钥长度集合（用于校验客户端上报的密钥）。
# AES_KEY_SIZE 是服务端自己生成密钥时用的长度；这里是入站校验的合法集合，
# 两者有意分开：服务端只生成 AES-256，但协议上仍接受客户端送来的其他合法长度。
AES_KEY_SIZES = frozenset({16, 24, 32})

# ── 主密钥（MASTER_KEY）策略 ──────────────────────────────────────────────
# MASTER_KEY 是 KEK 的熵来源，长度不足会直接削弱全部历史密文的安全性。
# 这个阈值同时是 generate_master_key() 的默认长度和启动前校验的下限，
# 三处必须一致，所以只在此定义一次。
MASTER_KEY_MIN_LENGTH = 32  # 字符

# ── HKDF / HMAC ──────────────────────────────────────────────────────────
# 从 AES 主密钥派生出的请求签名密钥长度（HMAC-SHA256，需与前端一致）
SIGNING_KEY_SIZE = 32  # 字节

# 盲索引密钥长度（HMAC-SHA256，服务端独立持有，不与 AES 密钥互相影响）
INDEX_KEY_SIZE = 32  # 字节

# 盲索引 token 的字节长度 —— 决定 DB 索引列的长度
BLIND_INDEX_DIGEST_SIZE = 16

# ── 请求签名（防重放）────────────────────────────────────────────────────
# 签名时间戳的允许偏差窗口，超出即视为重放并拒绝。
# 安全策略阈值：由中间件在调用处显式传入，本模块不给默认值。
SIGNATURE_TIMESTAMP_TOLERANCE_MS = 5 * 60 * 1000  # ±5 分钟

# ── 协议版本 ──────────────────────────────────────────────────────────────
ENCRYPTION_VERSION = "v1"  # 当前加密协议版本（EncryptedPayload.version）
CIPHERTEXT_FORMAT_VERSION = 0x01  # 字段密文的二进制格式版本（field_encryptor 首字节）
SUPPORTED_ENCRYPTION_VERSIONS = frozenset({ENCRYPTION_VERSION})
SUPPORTED_SIGNATURE_VERSIONS = frozenset({ENCRYPTION_VERSION})

# ── RSA-OAEP ──────────────────────────────────────────────────────────────
RSA_PUBLIC_EXPONENT = 65537  # RSA 标准公开指数，固定值
