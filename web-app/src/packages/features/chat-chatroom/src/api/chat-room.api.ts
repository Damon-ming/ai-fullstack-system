// web-app/src/packages/features/chat-chatroom/src/api/chat-room.api.ts
import { dataApi } from "@ming/data-layer";
import { netClient } from "@ming/biz-common-net-api";
import type {
  ChatRoomApiResponse,
  ChatRoomRequest,
  ChatSseMessage,
} from "./types";
import { createLogger } from "@ming/core-log";
import type {
  SseStreamCallbacks,
  SseStreamOptions,
  SseFinalState,
} from "@ming/biz-common-net-api";

const log = createLogger("chat-chatroom/api");

export const sendChatRoomMessageFn = (
  request: ChatRoomRequest,
  signal?: AbortSignal,
): Promise<ChatRoomApiResponse> => {
  log.debug("send request", {
    queryLength: request.query.length,
  });
  return dataApi.post("/api/llm/rag/answer/v1", request, { signal });
};

/**
 * SSE 流式请求 — 不走 TanStack，直接调 biz-common-net
 * callbacks：onMessage / onError / onComplete
 * opts：signal / extraHeaders / interceptors / parse / validateMessage / messageInterceptors
 */
export const streamChatRoomMessage = (
  request: ChatRoomRequest,
  callbacks: SseStreamCallbacks<ChatSseMessage>,
  opts?: SseStreamOptions<ChatSseMessage>,
): Promise<SseFinalState> => {
  return netClient.sseStream<ChatSseMessage>(
    "/api/llm/rag/stream/v1",
    request,
    callbacks,
    opts,
  );
};
