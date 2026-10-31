# app-server/src/com/damon/ming/router/knowledge/knowledge_router.py
"""
知识库目录树 —— 查看已上传资料的整体结构。

接口：
  GET /api/knowledge/tree/v1  获取知识库目录树 + 文件属性（size / created_at / sha256）

多用户共享知识库，所有登录用户看到同一份目录，不按用户过滤。
"""

from pathlib import Path

from fastapi import APIRouter, Request
from src.com.damon.ming.exception.error_codes import ErrorCode
from src.com.damon.ming.exception.server_error import get_safe_error_message
from src.com.damon.ming.log import pin
from src.com.damon.ming.middleware.rate_limiter import limiter
from src.com.damon.ming.router.knowledge.schemas.bean import KnowledgeNode
from src.com.damon.ming.schemas.response import (
    BaseBizFailedData,
    BaseFailedResponse,
    BaseSuccessResponse,
)
from src.com.damon.ming.utils.file_stat import file_creation_time, file_size
from src.com.damon.ming.utils.time import now_iso

logger = pin("knowledge.router")

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


def _build_tree(node_path: Path, rel_base: Path) -> KnowledgeNode:
    """递归构建目录树节点。

    Args:
        node_path: 当前节点的绝对路径。
        rel_base: 计算相对路径的基准目录（KNOWLEDGES_DIR）。

    Returns:
        带完整属性的 KnowledgeNode。
    """
    rel_path = (
        str(node_path.relative_to(rel_base).as_posix()) if node_path != rel_base else ""
    )

    if node_path.is_dir():
        children: list[KnowledgeNode] = []
        try:
            sorted_entries = sorted(node_path.iterdir())
        except PermissionError:
            logger.warning("目录无权限访问，跳过 | path=%s", node_path)
            sorted_entries = []

        for entry in sorted_entries:
            # 跳过残留临时文件
            if entry.is_file() and entry.suffix.endswith(".tmp"):
                continue
            children.append(_build_tree(entry, rel_base))

        return KnowledgeNode(
            name=node_path.name or "knowledge",
            type="directory",
            path=rel_path,
            size=0,
            created_at="",
            file_sha256="",
            children=children,
        )

    # 文件节点：补充 size / created_at / file_sha256
    try:
        size = file_size(node_path)
        created_iso = file_creation_time(node_path).isoformat()
    except OSError as e:
        logger.warning(
            "文件 stat 失败，使用默认值 | path=%s | error=%s", node_path.name, e
        )
        size = 0
        created_iso = ""

    return KnowledgeNode(
        name=node_path.name,
        type="file",
        path=rel_path,
        size=size,
        created_at=created_iso,
        file_sha256="",  # 首次版本不计算 sha，按需后续补充
    )


@router.get("/tree/v1", response_model=None)
@limiter.limit("30/minute")
def get_knowledge_tree(request: Request):
    """获取知识库目录树。

    返回完整目录结构，每个文件节点携带 size / created_at 属性。
    前端递归渲染 children 即可得到树形展示。
    """
    try:
        knowledge_dir = Path(request.app.state.system_config.knowledge_dir)
        if not knowledge_dir.exists():
            # 目录不存在时返回空树
            root = KnowledgeNode(
                name="knowledge",
                type="directory",
                path="",
                children=[],
            )
        else:
            root = _build_tree(knowledge_dir, knowledge_dir)

        return BaseSuccessResponse(
            code=ErrorCode.OK,
            data={
                "server_time": now_iso(),
                "root": root,
            },
        )
    except Exception as e:
        logger.exception("知识库目录查询失败")
        fail_data = BaseBizFailedData(error_msg=get_safe_error_message(e))
        return BaseFailedResponse(
            code=ErrorCode.SYSTEM.FILESYSTEM_FAILURE, data=fail_data
        )
