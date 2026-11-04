import type { DataApiResponse } from "@ming/data-layer";
/** 后端 LLM 实际返回内容（正文为纯文本，推理走 SSE reasoning 事件） */
export interface ChatRoomResult {
  /** 回答正文（纯文本，推理走 SSE reasoning 事件） */
  content: string;
  /** 会话 id；新会话由服务端生成，客户端回填后用于后续轮次追加 */
  conversationId?: string;
}
/** 后端 data 层：data 字段包裹 LLM 返回值（与 BaseLLMSuccessData 结构对齐） */
export interface ChatRoomSyncData {
  data: ChatRoomResult;
}
export type ChatRoomApiResponse = DataApiResponse<ChatRoomSyncData>;

/**
 * SSE 事件类型 —— 由 SSE 协议外层 event: 字段决定，
 * 不再嵌入 JSON payload（后端 StreamMessage 已去掉 event 字段）
 * - delta:    回答内容分片
 * - reasoning: 推理过程分片（reasoning=true 时）
 */
export type SseEvent = "start" | "delta" | "reasoning" | "done" | "error";

/** SSE start 事件携带的元信息（对应后端 ChatStartData） */
export interface ChatStartData {
  /** 本轮唯一标识，与历史记录 turnId 一致 */
  turnId: string;
  conversationId: string;
  /** 提问时刻（Unix 秒） */
  queryAt: number;
}

/**
 * 增量分片数据 —— 统一用 content 承载文本
 * event: delta   → 回答内容
 * event: reasoning → 推理过程
 */
export interface ChatDeltaData {
  content: string;
}
/**
 * SSE 错误事件数据 —— 与后端 BaseFailedResponse.data 对齐
 * 后端格式: { error_msg: string }
 */
export interface ChatSseErrorData {
  error_msg: string;
}
/**
 * SSE 消息体 —— JSON payload 解析结果。
 * 注意：不含 event 字段，事件类型由 SSE 协议 event: 字段决定（通过 meta.event 获取）。
 */
export interface ChatSseMessage {
  code: number;
  data:
    | ChatStartData
    | ChatDeltaData
    | ChatSseErrorData
    | Record<string, never>;
}
