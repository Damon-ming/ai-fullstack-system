// web-app/src/packages/features/search/src/api/index.ts
/**
 * Search API 层 —— 纯客户端搜索，无网络请求。
 *
 * 模块职责：
 *   - 提供搜索类型定义（types/）
 *   - 搜索逻辑由 hook/ 层实现（纯内存过滤）
 *
 * 不包含：
 *   - 网络请求（搜索为纯本地操作）
 */

export type * from "./types";
