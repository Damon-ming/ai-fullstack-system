# app-server/src/com/damon/ming/upload/router/upload_router.py
import json
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, Request, UploadFile
from src.com.damon.ming.log import pin
from src.com.damon.ming.router.upload.schemas.bean import (
    FileUploadFailedData,
    FileUploadRequest,
    FileUploadSuccessData,
)
from src.com.damon.ming.router.upload.service.upload_service import UploadService
from src.com.damon.ming.schemas.response import BaseFailedResponse, BaseSuccessResponse

logger = pin("upload.router")

router = APIRouter(prefix="/api/files", tags=["文件管理"])


@router.post("/upload/v1", response_model=None)
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
    try:
        # 优先从加密中间件注入的 decrypted_meta 读取（加密模式）
        # 否则回退到明文 meta_json（兼容未加密场景）
        meta = getattr(request.state, "decrypted_meta", None)
        if meta is None:
            meta = json.loads(meta_json) if meta_json else {}

        req_data = FileUploadRequest(**meta) if meta else FileUploadRequest()

        saved_files = await UploadService.batch_save_files(files, req_data)
        logger.info("文件上传请求完成 | saved_count=%s", len(saved_files))

        success_data = FileUploadSuccessData(
            server_time=datetime.now(tz=UTC).isoformat(), files=saved_files
        )
        return BaseSuccessResponse(code=10000, data=success_data)

    except Exception as e:  # noqa: BLE001
        logger.warning("文件上传请求失败")
        fail_data = FileUploadFailedData(error_msg=str(e))
        return BaseFailedResponse(code=40000, data=fail_data)
