import type { HistoryTurn } from "./response";

/** 保存会话请求：conversationId 缺省则新建；turns 整体替换 */
export interface SaveHistoryRequest {
  conversationId?: string;
  title: string;
  turns?: HistoryTurn[];
}
