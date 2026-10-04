import { useChatUiStore, useChatMessageStore } from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerNewChatHook() {
  const resetSession = useChatUiStore((s) => s.resetSession);
  const resetMessages = useChatMessageStore((s) => s.resetMessages);
  const setActiveId = useHistoryStore((s) => s.setActiveId);

  const newChat = () => {
    resetMessages();
    resetSession();
    setActiveId(null);
  };

  return { newChat };
}
