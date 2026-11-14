"""解密后的客户端会话密钥数据模型。"""

import time
from dataclasses import dataclass, field


@dataclass
class DecryptedSessionKey:
    """已解密的 AES 会话密钥及其有效期、使用时间。"""

    key_id: str
    aes_key: bytes
    ttl_seconds: int
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds

    def touch(self) -> None:
        self.last_used_at = time.time()
