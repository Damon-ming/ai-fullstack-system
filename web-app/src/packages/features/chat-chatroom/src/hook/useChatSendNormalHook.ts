import { useRef, useCallback } from "react";
import { useChatMessageStore } from "@ming/store/biz/chat-state";
import { sendChatRoomMessageFn } from "../api";
import type { ChatRoomRequest } from "../api/types";
import { useTranslation } from "@ming/i18n";
import { createLogger } from "@ming/core-log";

const log = createLogger("chat-chatroom/hook/sendNormal");

/** 同步一次性请求（保留备用） */
export function useChatSendNormalHook() {
  const { t } = useTranslation("chat-chatroom");
  const input = useChatMessageStore((s) => s.input);
  const setInput = useChatMessageStore((s) => s.setInput);
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const sending = useChatMessageStore((s) => s.sending);
  const setSending = useChatMessageStore((s) => s.setSending);

  /** 当前进行中的请求控制器，用于主动取消 */
  const abortControllerRef = useRef<AbortController | null>(null);

  /** 取消当前进行中的同步请求 */
  const abortNormal = useCallback(() => {
    if (abortControllerRef.current) {
      log.debug("abortNormal triggered");
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const sendNormal = async () => {
    const query = input.trim();
    if (!query || sending) {
      log.debug("sendNormal skipped", { hasQuery: Boolean(query), sending });
      return;
    }
    log.debug("sendNormal started", { queryLength: query.length });

    // 为本次请求创建独立的控制器（先取消上一次，防止并发）
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `assistant-${Date.now()}`;

    // 预先插入消息，补充role
    setMessages((items) => [
      ...items,
      { id: userMsgId, text: query, role: "user" },
      { id: assistantMsgId, text: t("reasoning"), role: "assistant" },
    ]);
    setInput("");
    setSending(true);

    try {
      const req: ChatRoomRequest = { query, reason: false };
      const res = await sendChatRoomMessageFn(req, controller.signal);
      log.debug("sendNormal succeeded");
      const result = res.data?.data;
      if (result) {
        setMessages((items) =>
          items.map((msg) =>
            msg.id === assistantMsgId
              ? { ...msg, text: result.answer_content }
              : msg,
          ),
        );
      }
    } catch (e) {
      // 被主动取消时不显示错误
      if (controller.signal.aborted) {
        log.debug("sendNormal aborted by user");
        return;
      }
      const errMsg =
        (e instanceof Error
          ? e.message
          : (e as { data?: { error_msg?: string } })?.data?.error_msg) ?? "";
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId ? { ...msg, text: errMsg } : msg,
        ),
      );
    } finally {
      abortControllerRef.current = null;
      setSending(false);
    }
  };

  return { sendNormal, abortNormal };
}
