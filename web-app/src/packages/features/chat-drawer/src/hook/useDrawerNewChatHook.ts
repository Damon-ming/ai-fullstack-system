import {
  useChatUiStore,
  useChatMessageStore,
} from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerNewChatHook() {
  const resetSession = useChatUiStore((s) => s.resetSession);
  const resetMessages = useChatMessageStore((s) => s.resetMessages);
  const abortStream = useChatMessageStore((s) => s.abortStream);
  const setActiveConversationId = useHistoryStore(
    (s) => s.setActiveConversationId,
  );

  const newChat = () => {
    // 新建会话前取消进行中的流，避免旧流的 sending 状态锁住新会话
    abortStream();
    resetMessages();
    resetSession();
    setActiveConversationId(null);
  };

  return { newChat };
}
