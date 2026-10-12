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

// 注：TanStack Mutation Hook 已移至 hook/useChatRoomMutation.ts

const log = createLogger("chat-chatroom/api");

// 同步接口 /api/llm/send/v1
export const sendChatRoomMessageFn = (
  request: ChatRoomRequest,
): Promise<ChatRoomApiResponse> => {
  log.debug("send request", {
    endpoint: "/api/llm/send/v1",
    queryLength: request.query.length,
  });
  return dataApi
    .post("/api/llm/send/v1", request)
    .then((response) => {
      log.debug("send response received");
      return response;
    })
    .catch((error) => {
      log.error("send request failed", error);
      throw error;
    });
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
    "/api/llm/chat/v1",
    request,
    callbacks,
    opts,
  );
};
