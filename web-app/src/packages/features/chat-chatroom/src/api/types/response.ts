import type { DataApiResponse } from "@ming/data-layer";
export interface ChatRoomSyncData {
  answer_content: string;
  thinking_process?: string;
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
