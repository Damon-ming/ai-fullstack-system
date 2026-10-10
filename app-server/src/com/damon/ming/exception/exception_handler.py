# app-server/src/com/damon/ming/exception/exception_handler.py
"""全局异常处理器 —— 兜底捕获未处理异常，防止堆栈泄露给客户端。

用法：在 main.py 中注册：
    from src.com.damon.ming.exception import register_exception_handler
    register_exception_handler(app)

子系统模块在初始化时注册自己的异常类型：
    from src.com.damon.ming.exception import register_exception, ServerSubSystem
    register_exception(DatabaseError, ServerSubSystem.DATABASE)
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.com.damon.ming.log import pin
from src.com.damon.ming.schemas.response import BaseFailedResponse
from src.com.damon.ming.exception.server_error import (
    classify_exception,
    get_safe_message,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = pin("app.exception")


def register_exception_handler(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI 应用。"""

    @app.exception_handler(Exception)
    async def handle_exception(request, exc: Exception):
        subsystem_code = classify_exception(exc)
        safe_msg = get_safe_message(subsystem_code)

        # 服务端记录完整堆栈（包含子系统分类）
        logger.exception(
            "未捕获异常 | subsystem=%d | path=%s | error=%s",
            subsystem_code,
            request.url.path,
            str(exc),
        )

        return JSONResponse(
            status_code=500,
            content=BaseFailedResponse(
                code=subsystem_code,
                data={"error_msg": safe_msg},
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request, exc: StarletteHTTPException):
        # FastAPI 的 HTTPException 保持原样返回（400/404 等）
        return JSONResponse(
            status_code=exc.status_code,
            content=BaseFailedResponse(
                code=exc.status_code,
                data={"error_msg": exc.detail},
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request, exc: RequestValidationError):
        logger.warning(
            "请求参数校验失败 | path=%s | errors=%s", request.url.path, exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content=BaseFailedResponse(
                code=422001,
                data={"error_msg": "请求参数格式错误"},
            ).model_dump(),
        )
