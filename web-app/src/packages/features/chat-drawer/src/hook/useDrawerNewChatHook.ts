import {
  useChatUiStore,
  useChatMessageStore,
} from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerNewChatHook() {
  const resetSession = useChatUiStore((s) => s.resetSession);
  const resetMessages = useChatMessageStore((s) => s.resetMessages);
  const setActiveConversationId = useHistoryStore(
    (s) => s.setActiveConversationId,
  );

  const newChat = () => {
    resetMessages();
    resetSession();
    setActiveConversationId(null);
  };

  return { newChat };
}
