import type { HistoryTurn } from "./response";

/** 保存会话请求：conversation_id 缺省则新建；turns 整体替换 */
export interface SaveHistoryRequest {
  conversation_id?: string;
  title: string;
  turns?: HistoryTurn[];
}
