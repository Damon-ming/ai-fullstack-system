# app-server/src/com/damon/ming/upload/router/upload_router.py
import json
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, UploadFile
from src.com.damon.ming.log import pin
from src.com.damon.ming.schemas.response import BaseFailedResponse, BaseSuccessResponse
from src.com.damon.ming.upload.schemas.bean import (
    FileUploadFailedData,
    FileUploadRequest,
    FileUploadSuccessData,
)
from src.com.damon.ming.upload.service.upload_service import (
    UploadService,
)

logger = pin("upload.router")

router = APIRouter(prefix="/api/files", tags=["文件管理"])


@router.post("/upload/v1", response_model=None)
async def save_files(
    files: list[UploadFile] = File(..., description="多文件"),  # noqa: B008
    meta_json: str = Form("", description="额外业务参数，JSON字符串"),
):
    logger.info(
        "文件上传请求开始 | file_count=%s | filenames=%s",
        len(files),
        [file.filename for file in files],
    )
    try:
        # 解析业务参数
        req_data = (
            FileUploadRequest(**json.loads(meta_json))
            if meta_json
            else FileUploadRequest()
        )

        # 调用service，路由不碰IO读写
        saved_files = await UploadService.batch_save_files(files, req_data)
        logger.info("文件上传请求完成 | saved_count=%s", len(saved_files))

        success_data = FileUploadSuccessData(
            server_time=datetime.now(tz=UTC).isoformat(), files=saved_files
        )
        return BaseSuccessResponse(bizCode=10000, data=success_data)

    except Exception as e:  # noqa: BLE001
        logger.warning("文件上传请求失败")
        fail_data = FileUploadFailedData(error_msg=str(e))
        return BaseFailedResponse(bizCode=40000, data=fail_data)
