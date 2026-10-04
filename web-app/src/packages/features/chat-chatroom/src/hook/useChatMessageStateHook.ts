import { useChatMessageStore } from "@ming/store/biz/chat-state";

/** 公共：消息状态 + 写入方法（同步/流式发送共用） */
export function useChatMessageStateHook() {
  const input = useChatMessageStore((s) => s.input);
  const setInput = useChatMessageStore((s) => s.setInput);
  const messages = useChatMessageStore((s) => s.messages);
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const sending = useChatMessageStore((s) => s.sending);
  const setSending = useChatMessageStore((s) => s.setSending);

  return { input, setInput, messages, setMessages, sending, setSending };
}
