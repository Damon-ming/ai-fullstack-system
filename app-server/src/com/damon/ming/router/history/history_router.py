"""
对话历史路由 —— 历史记录 CRUD + 分页。

接口：
  GET    /api/history/list/v1          分页获取历史记录列表
  GET    /api/history/v1/{conversation_id}  获取单条历史记录详情（含消息正文）
  POST   /api/history/save/v1          保存/更新对话历史（按 title 幂等）
  DELETE /api/history/v1/{conversation_id}  删除单条历史记录

所有接口从 request.state.ctx.token 获取用户身份，数据按 token 隔离。
"""

from fastapi import APIRouter, Path, Query, Request
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.history.schemas.bean import (
    HistoryDeleteSuccessData,
    HistoryFailedData,
    HistoryListSuccessData,
    HistorySaveRequest,
    HistorySaveSuccessData,
)
from src.com.damon.ming.router.history.service.history_service import HistoryService
from src.com.damon.ming.schemas.response import BaseFailedResponse, BaseSuccessResponse
from src.com.damon.ming.utils.time import now_iso

logger = pin("history.router")

router = APIRouter(prefix="/api/history", tags=["对话历史"])


def _token(request: Request) -> str:
    """从请求上下文获取当前用户 token。"""
    return getattr(request.state, "ctx", None) and request.state.ctx.token or ""


# ---------------------------------------------------------------------------
# 列表（分页）
# ---------------------------------------------------------------------------


@router.get("/list/v1", response_model=None)
@limiter.limit("30/minute")
def list_history(
    request: Request,
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """分页获取当前用户的对话历史列表（按 updated_time 倒序，不含消息正文）。"""
    token = _token(request)
    try:
        result = HistoryService.list_history(
            token=token, page=page, page_size=page_size
        )
        success_data = HistoryListSuccessData(
            server_time=now_iso(),
            items=result["items"],
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
        )
        return BaseSuccessResponse(code=ErrorCode.OK, data=success_data)
    except Exception as e:
        logger.exception("历史记录列表查询失败")
        fail_data = HistoryFailedData(error_msg=str(e))
        return BaseFailedResponse(
            code=ErrorCode.SYSTEM.DATABASE_FAILURE, data=fail_data
        )


# ---------------------------------------------------------------------------
# 详情
# ---------------------------------------------------------------------------


@router.get("/v1/{conversation_id}", response_model=None)
@limiter.limit("30/minute")
def get_history(
    request: Request,
    conversation_id: str = Path(..., description="对话 ID"),
):
    """获取单条历史记录详情（含消息正文）。"""
    token = _token(request)
    try:
        detail = HistoryService.get_history(
            conversation_id=conversation_id, token=token
        )
        if detail is None:
            return BaseFailedResponse(
                code=ErrorCode.HISTORY.NOT_FOUND,
                data=HistoryFailedData(error_msg=t(I18nKey.HISTORY_NOT_FOUND)),
            )
        return BaseSuccessResponse(
            code=ErrorCode.OK,
            data=HistorySaveSuccessData(server_time=now_iso(), conversation=detail),
        )
    except Exception as e:
        logger.exception("历史记录详情查询失败")
        fail_data = HistoryFailedData(error_msg=str(e))
        return BaseFailedResponse(
            code=ErrorCode.SYSTEM.DATABASE_FAILURE, data=fail_data
        )


# ---------------------------------------------------------------------------
# 保存（按 title 幂等更新）
# ---------------------------------------------------------------------------


@router.post("/save/v1", response_model=None)
@limiter.limit("10/minute")
def save_history(
    request: Request,
    body: HistorySaveRequest,
):
    """保存或更新对话历史。

    同一 token + title 已存在则更新消息；不存在则新建。
    """
    token = _token(request)
    try:
        detail = HistoryService.save_history(
            token=token,
            title=body.title,
            messages=body.messages,
        )
        return BaseSuccessResponse(
            code=ErrorCode.OK,
            data=HistorySaveSuccessData(server_time=now_iso(), conversation=detail),
        )
    except Exception as e:
        logger.exception("历史记录保存失败")
        fail_data = HistoryFailedData(error_msg=str(e))
        return BaseFailedResponse(code=ErrorCode.HISTORY.SAVE_FAILED, data=fail_data)


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


@router.delete("/v1/{conversation_id}", response_model=None)
@limiter.limit("10/minute")
def delete_history(
    request: Request,
    conversation_id: str = Path(..., description="对话 ID"),
):
    """删除单条历史记录。"""
    token = _token(request)
    try:
        deleted = HistoryService.delete_history(
            conversation_id=conversation_id, token=token
        )
        if not deleted:
            return BaseFailedResponse(
                code=ErrorCode.HISTORY.NOT_FOUND,
                data=HistoryFailedData(error_msg=t(I18nKey.HISTORY_NO_PERMISSION)),
            )
        return BaseSuccessResponse(
            code=ErrorCode.OK,
            data=HistoryDeleteSuccessData(
                server_time=now_iso(), deleted_id=conversation_id
            ),
        )
    except Exception as e:
        logger.exception("历史记录删除失败")
        fail_data = HistoryFailedData(error_msg=str(e))
        return BaseFailedResponse(code=ErrorCode.HISTORY.DELETE_FAILED, data=fail_data)
