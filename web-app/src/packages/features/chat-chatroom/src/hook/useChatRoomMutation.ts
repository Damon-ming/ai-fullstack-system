// web-app/src/packages/features/chat-chatroom/src/hook/useChatRoomMutation.ts
/**
 * 聊天消息发送 Mutation Hook —— TanStack Query 封装（缓存 + 重试策略）。
 *
 * 此层为状态管理（React hook），不属于 API 层职责。
 * API 层只负责 HTTP 调用，由 hook 层编排。
 */
import { QueryFactory } from "@ming/data-layer";
import { sendChatRoomMessageFn } from "../api";

export const useSendChatRoomMessage = QueryFactory.genMutationHook(
  sendChatRoomMessageFn,
  {
    retry: 0, // 发送聊天消息默认不重试，收敛在此处
  },
);
