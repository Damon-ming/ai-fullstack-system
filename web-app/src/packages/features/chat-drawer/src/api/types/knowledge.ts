/**
 * 知识库目录树 —— 类型定义。
 * 对应后端 KnowledgeNode schema 和 GET /api/knowledge/tree/v1 响应。
 */

/** 知识库目录树节点 */
export interface KnowledgeNode {
  /** 节点名称（目录名或文件名） */
  name: string;
  /** 节点类型：directory | file */
  type: "directory" | "file";
  /** 相对 knowledge_dir 的 POSIX 路径 */
  path: string;
  /** 文件大小（bytes），目录为 0 */
  size: number;
  /** 文件创建时间（ISO8601），目录为空 */
  created_at: string;
  /** 文件 SHA256，目录为空 */
  file_sha256: string;
  /** 子节点（仅 directory 类型） */
  children: KnowledgeNode[];
}

/** 知识库目录树接口响应数据 */
export interface KnowledgeTreeData {
  /** 服务器时间（ISO8601） */
  server_time: string;
  /** 根节点 */
  root: KnowledgeNode;
}
