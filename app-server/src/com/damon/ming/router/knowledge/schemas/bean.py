# app-server/src/com/damon/ming/router/knowledge/schemas/bean.py
"""
知识库目录树 —— 请求/响应 Schema。

一个接口同时返回目录结构和文件属性，前端递归渲染即可。
文件节点自带 size / created_at / file_sha256，无需额外 corpus 列表。
"""

from pydantic import BaseModel, Field


class KnowledgeNode(BaseModel):
    """知识库目录树节点。

    type="directory" 时 children 非空（空目录允许空列表）；
    type="file" 时 children 为空列表，文件属性挂在节点上。
    """

    name: str = Field(..., description="节点名称（目录名或文件名）")
    type: str = Field(..., description="节点类型：directory | file")
    path: str = Field("", description="相对 knowldeges/ 的路径，用于前端定位")
    size: int = Field(0, description="文件大小（bytes），目录为 0")
    created_at: str = Field("", description="文件创建时间（ISO8601），目录为空")
    file_sha256: str = Field("", description="文件 SHA256（后续删除/引用用），目录为空")
    children: list["KnowledgeNode"] = Field(
        default_factory=list, description="子节点（仅 directory 类型）"
    )
