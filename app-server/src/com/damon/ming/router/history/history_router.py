"""
对话历史路由 —— 历史记录 CRUD + 分页。

接口：
  GET    /api/history/list/v1          分页获取会话列表
  GET    /api/history/v1/{conversation_id}  获取单个会话详情（含全部轮次）
  POST   /api/history/save/v1          保存会话（按 conversation_id 幂等，整体替换轮次）
  DELETE /api/history/v1/{conversation_id}  删除会话及其轮次

所有接口从 request.state.ctx.token 获取用户身份，数据按 token 隔离。
响应 data 直接承载业务负载（列表返回数组、详情返回对象），与前端解包口径一致。
"""

from fastapi import APIRouter, Path, Query, Request
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.exception.server_error import get_safe_error_message
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.history.schemas.bean import (
    HistoryFailedData,
    HistorySaveRequest,
)
from src.com.damon.ming.router.history.service.history_service import HistoryService
from src.com.damon.ming.schemas.response import BaseFailedResponse, BaseSuccessResponse

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
    """分页获取当前用户的会话列表（按 updated_at 倒序，不含轮次正文）。"""
    token = _token(request)
    try:
        items = HistoryService.list_history(token=token, page=page, page_size=page_size)
        return BaseSuccessResponse(code=ErrorCode.OK, data=items)
    except Exception as e:
        logger.exception("历史记录列表查询失败")
        fail_data = HistoryFailedData(error_msg=get_safe_error_message(e))
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
    conversation_id: str = Path(..., description="会话 ID"),
):
    """获取单个会话详情（含全部轮次）。"""
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
        return BaseSuccessResponse(code=ErrorCode.OK, data=detail)
    except Exception as e:
        logger.exception("历史记录详情查询失败")
        fail_data = HistoryFailedData(error_msg=get_safe_error_message(e))
        return BaseFailedResponse(
            code=ErrorCode.SYSTEM.DATABASE_FAILURE, data=fail_data
        )


# ---------------------------------------------------------------------------
# 保存
# ---------------------------------------------------------------------------


@router.post("/save/v1", response_model=None)
@limiter.limit("10/minute")
def save_history(
    request: Request,
    body: HistorySaveRequest,
):
    """保存会话。

    conversation_id 为空则新建会话；非空则更新标题并整体替换轮次。
    """
    token = _token(request)
    try:
        detail = HistoryService.save_history(
            token=token,
            title=body.title,
            conversation_id=body.conversation_id,
            turns=body.turns,
        )
        if detail is None:
            return BaseFailedResponse(
                code=ErrorCode.HISTORY.NOT_FOUND,
                data=HistoryFailedData(error_msg=t(I18nKey.HISTORY_NO_PERMISSION)),
            )
        return BaseSuccessResponse(code=ErrorCode.OK, data=detail)
    except Exception as e:
        logger.exception("历史记录保存失败")
        fail_data = HistoryFailedData(error_msg=get_safe_error_message(e))
        return BaseFailedResponse(code=ErrorCode.HISTORY.SAVE_FAILED, data=fail_data)


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


@router.delete("/v1/{conversation_id}", response_model=None)
@limiter.limit("10/minute")
def delete_history(
    request: Request,
    conversation_id: str = Path(..., description="会话 ID"),
):
    """删除会话及其全部轮次。"""
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
            code=ErrorCode.OK, data={"deleted_id": conversation_id}
        )
    except Exception as e:
        logger.exception("历史记录删除失败")
        fail_data = HistoryFailedData(error_msg=get_safe_error_message(e))
        return BaseFailedResponse(code=ErrorCode.HISTORY.DELETE_FAILED, data=fail_data)
