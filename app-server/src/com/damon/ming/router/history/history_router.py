# app-server/src/com/damon/ming/router/history/history_router.py
"""
对话历史路由 —— 历史记录 CRUD + 分页。

接口：
  GET    /api/history/list/v1          分页获取会话列表
  GET    /api/history/v1/{conversation_id}  获取单个会话详情（轮次游标分页）
  DELETE /api/history/v1/{conversation_id}  删除会话及其轮次

所有接口从 request.state.client.user_id 获取用户身份，数据按 user_id 隔离。
响应 data 直接承载业务负载（列表返回数组、详情返回对象），与前端解包口径一致。
"""

from fastapi import APIRouter, HTTPException, Path, Query, Request
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.exception.server_error import get_safe_error_message
from src.com.damon.ming.i18n import t
from src.com.damon.ming.i18n.constants import I18nKey
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.history.history_store import (
    InvalidHistoryCursor,
    PinHistoryResult,
    UnpinHistoryResult,
)
from src.com.damon.ming.router.history.schemas.bean import (
    HistoryFailedData,
)
from src.com.damon.ming.router.history.service.history_service import HistoryService
from src.com.damon.ming.schemas.response import BaseFailedResponse, BaseSuccessResponse

logger = pin("history.router")

router = APIRouter(prefix="/api/history", tags=["对话历史"])


def _user_id(request: Request) -> int:
    """从请求上下文获取当前用户 user_id。"""
    return request.state.client.user_id


# ---------------------------------------------------------------------------
# 列表（分页）
# ---------------------------------------------------------------------------


@router.get("/list/v1", response_model=None)
@limiter.limit("30/minute")
def list_history(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="每页会话数"),
    cursor: str | None = Query(None, description="上一页返回的游标"),
):
    """游标分页获取当前用户的会话列表（按更新时间倒序）。"""
    user_id = _user_id(request)
    try:
        items = HistoryService.list_history(user_id=user_id, limit=limit, cursor=cursor)
        return BaseSuccessResponse(code=ErrorCode.OK, data=items)
    except InvalidHistoryCursor as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("历史记录列表查询失败")
        fail_data = HistoryFailedData(error_msg=get_safe_error_message(e))
        return BaseFailedResponse(
            code=ErrorCode.SYSTEM.DATABASE_FAILURE, data=fail_data
        )


@router.get("/search/v1", response_model=None)
@limiter.limit("30/minute")
def search_history(
    request: Request,
    keyword: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=50),
):
    """Search current user's conversations by title, query, or answer text."""
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return BaseSuccessResponse(code=ErrorCode.OK, data=[])
    try:
        items = HistoryService.search_history(
            _user_id(request), normalized_keyword, limit
        )
        return BaseSuccessResponse(code=ErrorCode.OK, data=items)
    except Exception as e:
        logger.exception("历史记录搜索失败")
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
    limit: int = Query(50, ge=1, le=100, description="每页轮数"),
    cursor: str | None = Query(None, description="上一页返回的游标"),
):
    """获取单个会话详情的一页轮次；不传 cursor 时从最早轮次开始。"""
    user_id = _user_id(request)
    try:
        detail = HistoryService.get_history(
            conversation_id=conversation_id,
            user_id=user_id,
            limit=limit,
            cursor=cursor,
        )
        if detail is None:
            return BaseFailedResponse(
                code=ErrorCode.HISTORY.NOT_FOUND,
                data=HistoryFailedData(error_msg=t(I18nKey.HISTORY_NOT_FOUND)),
            )
        return BaseSuccessResponse(code=ErrorCode.OK, data=detail)
    except InvalidHistoryCursor as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("历史记录详情查询失败")
        fail_data = HistoryFailedData(error_msg=get_safe_error_message(e))
        return BaseFailedResponse(
            code=ErrorCode.SYSTEM.DATABASE_FAILURE, data=fail_data
        )


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


@router.post("/v1/{conversation_id}/pin", response_model=None)
@limiter.limit("30/minute")
def pin_history(
    request: Request,
    conversation_id: str = Path(..., description="会话 ID"),
):
    """置顶当前用户的会话；每个用户最多置顶 30 个。"""
    try:
        result = HistoryService.pin_history(
            conversation_id=conversation_id,
            user_id=_user_id(request),
        )
        if result == PinHistoryResult.NOT_FOUND:
            return BaseFailedResponse(
                code=ErrorCode.HISTORY.NOT_FOUND,
                data=HistoryFailedData(error_msg=t(I18nKey.HISTORY_NOT_FOUND)),
            )
        if result == PinHistoryResult.LIMIT_REACHED:
            raise HTTPException(status_code=409, detail="最多置顶 30 个会话")
        return BaseSuccessResponse(
            code=ErrorCode.OK,
            data={"conversationId": conversation_id, "isPinned": True},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("历史会话置顶状态更新失败")
        fail_data = HistoryFailedData(error_msg=get_safe_error_message(e))
        return BaseFailedResponse(
            code=ErrorCode.SYSTEM.DATABASE_FAILURE, data=fail_data
        )


@router.delete("/v1/{conversation_id}/pin", response_model=None)
@limiter.limit("30/minute")
def unpin_history(
    request: Request,
    conversation_id: str = Path(..., description="会话 ID"),
):
    """取消置顶当前用户的会话。"""
    try:
        result = HistoryService.unpin_history(
            conversation_id=conversation_id,
            user_id=_user_id(request),
        )
        if result == UnpinHistoryResult.NOT_FOUND:
            return BaseFailedResponse(
                code=ErrorCode.HISTORY.NOT_FOUND,
                data=HistoryFailedData(error_msg=t(I18nKey.HISTORY_NOT_FOUND)),
            )
        return BaseSuccessResponse(
            code=ErrorCode.OK,
            data={"conversationId": conversation_id, "isPinned": False},
        )
    except Exception as e:
        logger.exception("历史会话取消置顶失败")
        fail_data = HistoryFailedData(error_msg=get_safe_error_message(e))
        return BaseFailedResponse(
            code=ErrorCode.SYSTEM.DATABASE_FAILURE, data=fail_data
        )


@router.delete("/v1/{conversation_id}", response_model=None)
@limiter.limit("10/minute")
def delete_history(
    request: Request,
    conversation_id: str = Path(..., description="会话 ID"),
):
    """删除会话及其全部轮次。"""
    user_id = _user_id(request)
    try:
        deleted = HistoryService.delete_history(
            conversation_id=conversation_id, user_id=user_id
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
