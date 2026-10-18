# app-server/src/com/damon/ming/upload/router/upload_router.py
import asyncio
import json

from fastapi import APIRouter, File, Form, Request, UploadFile
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.upload.schemas.bean import (
    FileUploadFailedData,
    FileUploadRequest,
    FileUploadSuccessData,
)
from src.com.damon.ming.router.upload.service.upload_service import UploadService
from src.com.damon.ming.schemas.response import BaseFailedResponse, BaseSuccessResponse
from src.com.damon.ming.utils.time import now

logger = pin("upload.router")

router = APIRouter(prefix="/api/files", tags=["文件管理"])


@router.post("/upload/v1", response_model=None)
@limiter.limit("5/minute")
async def save_files(
    request: Request,
    files: list[UploadFile] = File(..., description="多文件"),  # noqa: B008
    meta_json: str = Form("", description="额外业务参数，JSON字符串"),
):
    logger.info(
        "文件上传请求开始 | file_count=%s | filenames=%s",
        len(files),
        [file.filename for file in files],
    )

    # 创建请求级上下文，绑定 CancellationToken
    ctx = request.app.state.pool_mgr.create_request_context()

    try:
        # 优先从加密中间件注入的 decrypted_meta 读取（加密模式）
        # 否则回退到明文 meta_json（兼容未加密场景）
        meta = getattr(request.state, "decrypted_meta", None)
        if meta is None:
            meta = json.loads(meta_json) if meta_json else {}

        req_data = FileUploadRequest(**meta) if meta else FileUploadRequest()

        # 复用 document 命名池写盘，统一线程资源管理
        document_pool = request.state.pool_mgr.get_pool("document")
        saved_files = await UploadService.batch_save_files(
            files,
            req_data,
            upload_config=request.app.state.upload_config,
            cancellation_token=ctx.cancellation_token,
            executor=document_pool,
        )
        logger.info("文件上传请求完成 | saved_count=%s", len(saved_files))

        success_data = FileUploadSuccessData(
            server_time=now().isoformat(), files=saved_files
        )
        return BaseSuccessResponse(code=ErrorCode.OK, data=success_data)

    except asyncio.CancelledError:
        logger.warning("【统计】文件上传请求被客户端主动取消（断网/关闭页面/强制结束）")
        raise
    except Exception as e:
        logger.exception("文件上传请求失败")
        fail_data = FileUploadFailedData(error_msg=str(e))
        return BaseFailedResponse(code=ErrorCode.UPLOAD.UPLOAD_FAILED, data=fail_data)
    finally:
        # 请求结束（无论成功/失败/取消）：清理请求上下文，回收线程资源
        ctx.cleanup()
