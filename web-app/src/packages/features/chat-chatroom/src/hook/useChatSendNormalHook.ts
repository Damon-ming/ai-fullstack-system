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

  const sendNormal = async () => {
    const query = input.trim();
    if (!query || sending) {
      log.debug("sendNormal skipped", { hasQuery: Boolean(query), sending });
      return;
    }
    log.debug("sendNormal started", { queryLength: query.length });

    const userMsgId = `user-${Date.now()}`;
    const assistantMsgId = `assistant-${Date.now()}`;

    // 预先插入消息，补充role
    setMessages((items) => [
      ...items,
      { id: userMsgId, text: query, role: "user" },
      { id: assistantMsgId, text: t("thinking"), role: "assistant" },
    ]);
    setInput("");
    setSending(true);

    try {
      const req: ChatRoomRequest = { query, think: false };
      const res = await sendChatRoomMessageFn(req);
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
      log.error("sendNormal failed", e);
      const errMsg = e instanceof Error ? e.message : t("error.sendFailed");
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId ? { ...msg, text: errMsg } : msg,
        ),
      );
    } finally {
      setSending(false);
    }
  };

  return { sendNormal };
}
