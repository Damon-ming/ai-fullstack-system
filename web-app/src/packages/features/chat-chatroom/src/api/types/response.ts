import type { BizApiResponse } from "@ming/biz-common-net-api";
export interface ChatRoomSyncData {
  answer_content: string;
  thinking_process?: string;
}
export type ChatRoomApiResponse = BizApiResponse<ChatRoomSyncData>;
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
