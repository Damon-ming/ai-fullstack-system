import type { DataApiResponse } from "@ming/data-layer";
/** 后端 LLM 实际返回内容 */
export interface ChatRoomResult {
  answer_content: string;
  thinking_process?: string;
}
/** 后端 data 层：result 字段包裹 LLM 返回值（与 BaseLLMSuccessData 结构对齐） */
export interface ChatRoomSyncData {
  result: ChatRoomResult;
}
export type ChatRoomApiResponse = DataApiResponse<ChatRoomSyncData>;
export type SseEvent = "delta" | "done" | "error";
export interface ChatDeltaData {
  answer_content: string;
  thinking_process?: string;
}
export interface ChatSseErrorData {
  error_msg: string;
  error_code?: string;
}
export interface ChatSseMessage {
  bizCode: number;
  event: SseEvent;
  data: ChatDeltaData | ChatSseErrorData | Record<string, never>;
}
