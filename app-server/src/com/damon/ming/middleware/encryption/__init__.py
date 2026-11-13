# app-server/src/com/damon/ming/middleware/encryption/__init__.py
"""HTTP 加密处理链。

把原来挤在 EncryptionMiddleware.dispatch 里的 6 个步骤拆成一条
gate 链：每个 gate 只负责一个决策，命中即返回（链上后续 gate 不再
执行），否则交给下一环。新增处理步骤 = 新增一个 gate 类 +
build_encryption_chain() 里加一行。

一次请求穿过两层：
  inbound  —— 白名单 / 开关 / 版本校验 / 解密验签，决定是否把请求交给下游
  outbound —— 响应加密，决定下游响应是否加密后返回

模块划分：
  context.py   — 链上共享上下文（请求 / 会话 / 下游调用）
  chain.py     — gate 接口与管道运行器
  gates.py     — 各决策层（白名单 / 开关 / 版本 / 解密 / 响应加密）
  decrypt.py   — inbound 解密策略（JSON / FormData，平级）
  encrypt.py   — outbound 加密策略（restful / SSE，平级）
  responses.py — 拒绝响应工厂 + 协议版本校验
  wire.py      — 线格式判定与小工具
  nonce.py     — nonce 重放防护缓存
  sse.py       — SSE 字节流逐事件加密
"""

from src.com.damon.ming.middleware.encryption.chain import (
    EncryptionChain,
    EncryptionGate,
)
from src.com.damon.ming.middleware.encryption.context import EncryptionContext
from src.com.damon.ming.middleware.encryption.decrypt import (
    DecryptStrategy,
    FormDataDecryptStrategy,
    JsonDecryptStrategy,
)
from src.com.damon.ming.middleware.encryption.encrypt import (
    EncryptStrategy,
    JsonEncryptStrategy,
    SseEncryptStrategy,
)
from src.com.damon.ming.middleware.encryption.gates import (
    DecryptGate,
    EncryptionSwitchGate,
    EncryptionVersionGate,
    ResponseEncryptGate,
    SignatureVersionGate,
    WhitelistGate,
)
from src.com.damon.ming.middleware.encryption.nonce import NonceCache, get_nonce_cache

__all__ = [
    "DecryptGate",
    "DecryptStrategy",
    "EncryptStrategy",
    "EncryptionChain",
    "EncryptionContext",
    "EncryptionGate",
    "EncryptionSwitchGate",
    "EncryptionVersionGate",
    "FormDataDecryptStrategy",
    "JsonDecryptStrategy",
    "JsonEncryptStrategy",
    "NonceCache",
    "ResponseEncryptGate",
    "SignatureVersionGate",
    "SseEncryptStrategy",
    "WhitelistGate",
    "build_encryption_chain",
]


def build_encryption_chain() -> EncryptionChain:
    """组装默认加密处理链（列表顺序即执行顺序，靠前的先执行）。"""
    nonce_cache = get_nonce_cache()
    return EncryptionChain(
        gates=[
            # ── inbound ──────────────────────────────────────────────
            # 1. 白名单：明文放行
            WhitelistGate(),
            # 2. 开关：debug 放行 / release 必须加密
            EncryptionSwitchGate(),
            # 3. 协议版本校验（不解密即可拒绝）
            EncryptionVersionGate(),
            SignatureVersionGate(),
            # 4. 解密 + 验签（策略：JSON / FormData）
            DecryptGate(
                strategies=[
                    JsonDecryptStrategy(nonce_cache),
                    FormDataDecryptStrategy(nonce_cache),
                ]
            ),
            # ── outbound ─────────────────────────────────────────────
            # 5. 响应加密（策略：restful / SSE；链的最后一环，
            #    next_gate 即下游应用，因此短路会完全绕过它）
            ResponseEncryptGate(
                strategies=[
                    JsonEncryptStrategy(),
                    SseEncryptStrategy(),
                ]
            ),
        ]
    )
