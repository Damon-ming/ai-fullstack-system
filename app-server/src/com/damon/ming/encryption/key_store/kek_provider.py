# app-server/src/com/damon/ming/encryption/key_store/kek_provider.py
"""
KEK (Key Encryption Key) 提供者 —— 从环境变量派生加密密钥。

职责：
  - 从环境变量 MASTER_KEY 派生 KEK
  - 用 HKDF-SHA256 从主密钥 + salt 派生出固定长度的 AES-256 密钥
  - 用于加密存储到 DB 的 AES 会话密钥（加密后落盘）

安全要点：
  - MASTER_KEY 至少 32 字符，生产环境应使用强随机密钥
  - salt 固定（写在代码里），确保同一 MASTER_KEY 始终派生同一 KEK
  - KEK 只在内存中持有，不落盘

为什么不直接用 RSA 私钥加密？
  - RSA 私钥重启后会重新生成（当前实现），无法解密旧数据
  - KEK 从环境变量派生，只要 MASTER_KEY 不变，重启后仍能解密历史会话

**HKDF = HMAC-based Key Derivation Function，基于 HMAC 的密钥派生函数**
它的作用：**把一个原始密钥材料（输入），安全地 “衍生” 出一个或多个符合密码学规范、固定长度的密钥**。

原始输入（比如你的 `MASTER_KEY`）可能长度、格式不标准；HKDF 把它转换成规范的、适合 AES 使用的密钥。
HKDF 分为两步：

1. **Extract（提取）**：`master_key + salt` → 得到伪随机密钥
2. **Expand（扩展）**：把上面的结果 + `info` → 输出指定长度的密钥（这里输出 32 字节，AES256）

1. MASTER_KEY 丢失：**所有历史密文无法解密，数据永久丢失**
2. MASTER_KEY 泄露：**全部历史密文可以被攻击者解密，数据泄露**
3. 单个 AES 会话密钥泄露：仅影响该会话的数据，风险隔离。
"""

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# 固定 salt —— 确保同一 MASTER_KEY 始终派生同一 KEK
# 生产环境可以改为从环境变量读取，但固定值更便于运维
# 字节类型（bytes）
KEK_SALT = b"damon-common-key-store-v1"
# `info` 是**上下文 / 标识信息，用来区分不同用途的密钥**。
# - 同样的 master_key + salt，如果`info`不一样，**派生出来的密钥完全不一样**
# - 语义上标记：**这个派生出来的密钥，专门用来做「会话密钥封装」**
# info**不需要保密**，是明文业务标记。
KEK_INFO = b"encryption-session-key-wrap"
KEK_LENGTH = 32  # AES-256


def derive_kek(master_key: str | None = None) -> bytes:
    """从 MASTER_KEY 环境变量派生 KEK。

    参数：
      master_key: 主密钥。为 None 时从 MASTER_KEY 环境变量读取。

    返回：
      32 字节 AES-256 密钥
    """
    if master_key is None:
        master_key = os.environ.get("MASTER_KEY", "")

    if not master_key:
        from src.com.damon.ming.exception import EncryptionError

        raise EncryptionError(
            "MASTER_KEY 环境变量未设置。请设置一个至少 32 字符的随机密钥。"
        )

    if len(master_key) < 16:
        from com.damon.ming.log.logger import security_warn

        security_warn("MASTER_KEY 长度不足 32 字符，生产环境请使用更强的密钥")

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=KEK_LENGTH,
        salt=KEK_SALT,
        info=KEK_INFO,
    )
    return hkdf.derive(master_key.encode("utf-8"))


def wrap_key(aes_key: bytes, kek: bytes) -> str:
    """用 KEK 加密 AES 会话密钥，返回 base64 编码的密文。

    格式与 crypto_engine.EncryptedPayload 一致：
      { "encrypted": base64, "nonce": base64 }

    使用 AES-256-GCM，每次加密随机生成 nonce。
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    ciphertext = AESGCM(kek).encrypt(nonce, aes_key, None)

    # `nonce + ciphertext` 是**原始二进制 bytes**，数据库、JSON 不适合直接存二进制；
    # `base64` 把二进制转成**纯 ASCII 字符串**，方便存入数据库 / JSON 返回。
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def unwrap_key(wrapped_b64: str, kek: bytes) -> bytes:
    """解密 wrap_key 的结果，返回原始 AES 密钥字节。

    认证失败（密文被篡改 / KEK 错误）会抛出 InvalidTag。
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(wrapped_b64)
    nonce = raw[:12]
    ciphertext = raw[12:]

    return AESGCM(kek).decrypt(nonce, ciphertext, None)
