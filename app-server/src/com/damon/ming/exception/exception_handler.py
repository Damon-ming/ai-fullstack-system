# app-server/src/com/damon/ming/exception/exception_handler.py
"""全局异常处理器 —— 兜底捕获未处理异常，防止堆栈泄露给客户端。

用法：在 main.py 中注册：
    from src.com.damon.ming.exception import register_exception_handler
    register_exception_handler(app)

子系统模块在初始化时注册自己的异常类型：
    from src.com.damon.ming.exception import register_exception, ServerSubSystem
    register_exception(DatabaseError, ServerSubSystem.DATABASE)

确保所有返回给客户端的 JSON 都携带统一业务码，不直接使用 HTTP 状态码作为 code。
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.com.damon.ming.exception.error_codes import ErrorCode, format_code
from src.com.damon.ming.exception.server_error import (
    classify_exception,
    get_safe_error_message,
    get_safe_message,
)
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.schemas.response import BaseBizFailedData, BaseFailedResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = pin("app.exception")

# HTTP 状态码 → 业务码映射
# 确保任何路径下客户端收到的都是统一业务码，而非原始 HTTP 状态码
_HTTP_STATUS_TO_BIZ_CODE: dict[int, int] = {
    400: ErrorCode.VALIDATION.PARAM_FORMAT,  # 400 → 参数错误
    404: ErrorCode.SYSTEM.UNKNOWN,  # 404 → 未知（路由不存在）
    405: ErrorCode.SYSTEM.UNKNOWN,  # 405 → 未知（方法不允许）
    408: ErrorCode.CHAT.TIMEOUT,  # 408 → 超时
    413: ErrorCode.UPLOAD.UPLOAD_FAILED,  # 413 → 上传失败（payload 过大）
    429: ErrorCode.SYSTEM.UNKNOWN,  # 429 → 未知（限流）
}


def _map_http_status_to_biz_code(status_code: int) -> int:
    """将 HTTP 状态码映射为统一业务码，兜底为 SYSTEM.UNKNOWN。"""
    return _HTTP_STATUS_TO_BIZ_CODE.get(status_code, ErrorCode.SYSTEM.UNKNOWN)


def register_exception_handler(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI 应用。"""

    @app.exception_handler(Exception)
    async def handle_exception(request, exc: Exception):
        # 优先使用异常自身携带的业务码（抛出时明确指定了具体原因）
        biz_code = getattr(exc, "biz_code", None)
        if biz_code is not None:
            code = biz_code
            safe_msg = get_safe_error_message(exc)
        else:
            # 兜底：按异常类型分类到子系统
            code = classify_exception(exc)
            safe_msg = get_safe_message(code)

        # 服务端记录完整堆栈（包含子系统分类）
        logger.exception(
            "未捕获异常 | code=%s | path=%s | error=%s",
            format_code(code),
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=500,
            content=BaseFailedResponse(
                code=code,
                data=BaseBizFailedData(error_msg=safe_msg),
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request, exc: StarletteHTTPException):
        # 将 HTTP 状态码映射为统一业务码，不使用原始 HTTP 状态码
        biz_code = _map_http_status_to_biz_code(exc.status_code)

        logger.warning(
            "HTTP 异常 | http_status=%d | biz_code=%s | path=%s | detail=%s",
            exc.status_code,
            format_code(biz_code),
            request.url.path,
            exc.detail,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=BaseFailedResponse(
                code=biz_code,
                data=BaseBizFailedData(error_msg=exc.detail),
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request, exc: RequestValidationError):
        logger.warning(
            "请求参数校验失败 | path=%s | code=%s | errors=%s",
            request.url.path,
            format_code(ErrorCode.VALIDATION.PARAM_FORMAT),
            exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content=BaseFailedResponse(
                code=ErrorCode.VALIDATION.PARAM_FORMAT,
                data=BaseBizFailedData(error_msg=t(I18nKey.VALIDATION_PARAM_FORMAT)),
            ).model_dump(),
        )
