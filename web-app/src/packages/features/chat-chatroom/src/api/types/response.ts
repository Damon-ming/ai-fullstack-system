import type { DataApiResponse } from "@ming/data-layer";
/** 后端 LLM 实际返回内容 */
export interface ChatRoomResult {
  answer_content: string;
  thinking_process?: string;
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
 * - thinking: 思考过程分片（think=true 时）
 */
export type SseEvent = "start" | "delta" | "thinking" | "done" | "error";

/** SSE start 事件携带的元信息（对应后端 ChatStartData / StartMetadata） */
export interface ChatStartData {
  msgId: string;
  conversationId: string;
  model: string;
  createdAt: number;
  traceId: string;
}

/**
 * 增量分片数据 —— 统一用 content 承载文本
 * event: delta   → 回答内容
 * event: thinking → 思考过程
 */
export interface ChatDeltaData {
  content: string;
}
export interface ChatSseErrorData {
  error_msg: string;
  error_code?: string;
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
