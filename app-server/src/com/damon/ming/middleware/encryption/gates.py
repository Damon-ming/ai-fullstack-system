# app-server/src/com/damon/ming/middleware/encryption/gates.py
"""加密处理链的各决策层。

链的顺序（build_encryption_chain 中组装，靠前的先执行）：
  WhitelistGate            白名单 → 明文放行
  EncryptionSwitchGate     开关判定（debug 放行 / release 400）
  EncryptionVersionGate    加密协议版本校验
  SignatureVersionGate     签名协议版本校验
  DecryptGate              按 content-type 选解密策略（inbound）
  ResponseEncryptGate      按响应类型选加密策略（outbound）

每个 gate 只做一个决策：命中就返回（链上后续 gate 不执行），
否则 await next_gate() 交给下一环。
格式分派（JSON / FormData、restful / SSE）由 gate 持有的平级策略表
完成，见 decrypt.py / encrypt.py。
"""

from collections.abc import Sequence

from src.com.damon.ming.debug import is_debug
from src.com.damon.ming.exception import EncryptionError
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.encryption.chain import EncryptionGate, GateCall
from src.com.damon.ming.middleware.encryption.context import EncryptionContext
from src.com.damon.ming.middleware.encryption.decrypt import DecryptStrategy
from src.com.damon.ming.middleware.encryption.encrypt import EncryptStrategy
from src.com.damon.ming.middleware.encryption.responses import (
    check_signature_version_header,
    check_version_header,
    encryption_required_response,
    unsupported_signature_version_response,
    unsupported_version_response,
)
from src.com.damon.ming.middleware.encryption.wire import is_whitelisted
from starlette.responses import Response

logger = pin("middleware.encryption")


# ---------------------------------------------------------------------------
# 1. 白名单
# ---------------------------------------------------------------------------


class WhitelistGate(EncryptionGate):
    """白名单：明文放行（不解密、不加密响应）。

    白名单是环境无关的 HTTP 路由策略，由系统配置提供。
    """

    async def handle(self, ctx: EncryptionContext, next_gate: GateCall) -> Response:
        whitelist = ctx.request.app.state.config.system_config.whitelist
        if not is_whitelisted(ctx.path, whitelist):
            return await next_gate()
        logger.debug("加密白名单命中，明文放行 | path=%s", ctx.path)
        return await ctx.call_downstream()


# ---------------------------------------------------------------------------
# 2. 开关判定
# ---------------------------------------------------------------------------


class EncryptionSwitchGate(EncryptionGate):
    """加密开关判定（服务端主导）。

    X-Encrypt-Enabled 由客户端声明，是否接受由服务端按环境决定：
      debug  ：客户端未声明加密 → 明文放行（前端可调试开关）
      release：客户端未声明加密 → 400（必须加密，fail-closed）

    release 下直接返回错误、不调用下游：既不为来路不明的请求服务，
    也不消耗下游算力，更不会把响应加密后发回去。
    """

    async def handle(self, ctx: EncryptionContext, next_gate: GateCall) -> Response:
        if ctx.enc.enabled:
            return await next_gate()

        if not is_debug():
            logger.warning(
                "release 模式，客户端未开启加密 | path=%s client=%s",
                ctx.path,
                ctx.request.client.host if ctx.request.client else "unknown",
            )
            return encryption_required_response()

        logger.debug("debug 模式，客户端未开启加密，明文放行 | path=%s", ctx.path)
        return await ctx.call_downstream()


# ---------------------------------------------------------------------------
# 3. 协议版本校验（header 层级，不解密即可拒绝）
# ---------------------------------------------------------------------------


class EncryptionVersionGate(EncryptionGate):
    """加密协议版本校验（X-Encrypt-Version）。"""

    async def handle(self, ctx: EncryptionContext, next_gate: GateCall) -> Response:
        error = check_version_header(ctx.enc.version)
        if error is None:
            return await next_gate()
        i18n_key, i18n_params = error
        logger.warning("加密版本校验失败: %s | path=%s", i18n_key, ctx.path)
        return unsupported_version_response(i18n_key, i18n_params)


class SignatureVersionGate(EncryptionGate):
    """签名协议版本校验（X-Signature-Version）。"""

    async def handle(self, ctx: EncryptionContext, next_gate: GateCall) -> Response:
        error = check_signature_version_header(ctx.enc.signature_version)
        if error is None:
            return await next_gate()
        i18n_key, i18n_params = error
        logger.warning("签名版本校验失败: %s | path=%s", i18n_key, ctx.path)
        return unsupported_signature_version_response(i18n_key, i18n_params)


# ---------------------------------------------------------------------------
# 4. 解密 + 验签（inbound）
# ---------------------------------------------------------------------------


class DecryptGate(EncryptionGate):
    """按 content-type 选择解密策略；都不匹配 → 400。

    策略表（JSON / FormData）是平级的，命中的策略直接决定继续还是拒绝：
    解密成功后需要「继续走后面的响应加密层」，平级 gate 的 next_gate()
    无法表达「本组已处理、同组其它 gate 跳过」，策略表天然满足这一点。
    """

    def __init__(self, strategies: Sequence[DecryptStrategy]) -> None:
        self._strategies = tuple(strategies)

    async def handle(self, ctx: EncryptionContext, next_gate: GateCall) -> Response:
        for strategy in self._strategies:
            if strategy.supports(ctx):
                response = await strategy.apply(ctx)
                if response is not None:
                    return response
                return await next_gate()

        # 声明加密但没有可解密的 body（如异常情况下 GET 携带加密头）
        logger.warning(
            "请求未携带可解密的 body | path=%s content_type=%s",
            ctx.path,
            ctx.content_type,
        )
        return encryption_required_response()


# ---------------------------------------------------------------------------
# 5. 响应加密（outbound）
# ---------------------------------------------------------------------------


class ResponseEncryptGate(EncryptionGate):
    """响应加密：按响应类型选择加密策略（restful 整体 / SSE 逐事件）。

    这是链上最后一环（最内层），next_gate() 即终端（调用下游应用）。
    正因为它最内层，白名单 / debug 开关的短路才完全绕过它。
    """

    def __init__(self, strategies: Sequence[EncryptStrategy]) -> None:
        self._strategies = tuple(strategies)

    async def handle(self, ctx: EncryptionContext, next_gate: GateCall) -> Response:
        response = await next_gate()

        session = ctx.session
        if session is None:
            # 明文链路（白名单 / debug 开关）已在前面短路，正常不可达；
            # 仍 fail-closed：绝不因为内部状态异常而回退明文。
            raise EncryptionError(
                "响应加密失败：缺少加密会话",
                biz_code=ErrorCode.ENCRYPT.ENCRYPTION_RESPONSE_FAILED,
            )

        for strategy in self._strategies:
            if strategy.supports(response):
                return await strategy.apply(ctx, response, session)

        # 其它响应类型（文件下载、健康检查等）原样返回
        return response
