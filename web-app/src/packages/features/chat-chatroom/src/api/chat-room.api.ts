// web-app/src/packages/features/chat-chatroom/src/api/chat-room.api.ts
import { dataApi, QueryFactory } from "@ming/data-layer";
import type {
  ChatRoomApiResponse,
  ChatRoomRequest,
  ChatSseMessage,
} from "./types";
import { createLogger } from "@ming/core-log";
import type {
  ErrDataResponse,
  SseStreamCallbacks,
  SseStreamOptions,
  SseFinalState,
} from "@ming/biz-common-net-api";

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

export const sendChatRoomMessage = sendChatRoomMessageFn;

export const useSendChatRoomMessage = QueryFactory.genMutationHook(
  sendChatRoomMessageFn,
  {
    retry: 0, // 发送聊天消息默认不重试，收敛在此处
  },
);

/**
 * 命令式调用（适配新签名：callbacks + opts）
 * - callbacks：onMessage / onError / onComplete
 * - opts：signal / extraHeaders / interceptors(单次请求拦截器) / parse / validateMessage / messageInterceptors
 */
export const streamChatRoomMessage = (
  request: ChatRoomRequest,
  callbacks: SseStreamCallbacks<ChatSseMessage>,
  opts?: SseStreamOptions<ChatSseMessage>,
): Promise<SseFinalState> => {
  return dataApi.sse<ChatSseMessage>(
    "/api/llm/chat/v1",
    request,
    callbacks,
    opts,
  );
};