# app-server/src/com/damon/ming/middleware/encryption/nonce.py
"""nonce 重放防护缓存。

原先是中间件上的 ClassVar；改成独立对象后由处理链持有，生命周期
与链一致（启动时创建一次，进程内共享）。

缓存键 = "session_key_id:nonce"，值 = 首次接收时间戳（秒）。
TTL 取签名容差的两倍，过期即移除，避免同一 nonce 在容差窗口外被误判为重放。
"""

import asyncio
import time
from collections import OrderedDict

# 10 分钟（2 × 5 分钟签名容差）
DEFAULT_TTL_SECONDS = 600
# LRU 上限
DEFAULT_MAX_SIZE = 10_000
# 超限时淘汰最老的 20%
DEFAULT_EVICT_RATIO = 0.2


class NonceCache:
    """nonce 新鲜度缓存：同一会话 + 同一 nonce 在 TTL 内只接受一次。"""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_size: int = DEFAULT_MAX_SIZE,
        evict_ratio: float = DEFAULT_EVICT_RATIO,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._evict_ratio = evict_ratio
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._lock: asyncio.Lock | None = None

    def _ensure_lock(self) -> asyncio.Lock:
        """惰性创建锁（首次请求时绑定到当前事件循环）。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def check_and_store(self, session_key_id: str, nonce: str) -> bool:
        """检查 nonce 是否已使用过，未使用则记录。

        Returns:
            True  = nonce 新鲜，可以继续
            False = nonce 已存在（重放），拒绝请求
        """
        cache_key = f"{session_key_id}:{nonce}"
        now = time.time()

        async with self._ensure_lock():
            if cache_key in self._cache:
                first_seen = self._cache[cache_key]
                if now - first_seen < self._ttl_seconds:
                    return False  # 重放命中
                # 已过期，移除后重新记录
                del self._cache[cache_key]

            self._cache[cache_key] = now
            self._cache.move_to_end(cache_key)

            if len(self._cache) > self._max_size:
                evict_count = int(self._max_size * self._evict_ratio)
                for _ in range(evict_count):
                    self._cache.popitem(last=False)

        return True


# 进程级单例：重放防护必须跨中间件实例生效（与原先挂在中间件类上的
# ClassVar 语义一致），否则多实例部署时同一 nonce 可被重复使用。
_DEFAULT_CACHE: NonceCache | None = None


def get_nonce_cache() -> NonceCache:
    """获取进程级 nonce 缓存（首次调用时创建）。"""
    global _DEFAULT_CACHE
    if _DEFAULT_CACHE is None:
        _DEFAULT_CACHE = NonceCache()
    return _DEFAULT_CACHE
