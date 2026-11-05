// web-app/src/packages/features/chat-drawer/src/hook/useDrawerHistoryHook.ts
import { useHistory, turnsToChatMessages } from "@ming/feature-history-api";
import {
  useChatMessageStore,
  useChatUiStore,
} from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerHistoryHook() {
  const activeConversationId = useHistoryStore((s) => s.activeConversationId);
  const setActiveConversationId = useHistoryStore(
    (s) => s.setActiveConversationId,
  );
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const abortStream = useChatMessageStore((s) => s.abortStream);
  const resetSession = useChatUiStore((s) => s.resetSession);
  const {
    list,
    groups,
    getTurns,
    remove,
    hasMore,
    loadMore,
    isLoadingMore,
    loading,
  } = useHistory();

  const selectChat = async (id: string) => {
    // 切换会话前取消进行中的流，避免旧流的 sending 状态锁住新会话
    abortStream();
    // 无论有无轮次都切换视图：空会话 / 拉取失败是合法状态，
    // 静默保留旧会话内容会让用户误以为在看新会话
    const turns = await getTurns(id);
    setMessages(turnsToChatMessages(turns));
    setActiveConversationId(id);
    resetSession();
  };

  const deleteHistory = (id: string) => {
    remove(id);
    // 删除的是当前会话时必须清空 activeConversationId，否则下一轮发送会按该 id 重新建会话
    if (activeConversationId === id) setActiveConversationId(null);
  };

  return {
    list,
    groups,
    activeConversationId,
    loading,
    selectChat,
    deleteHistory,
    hasMore,
    loadMore,
    isLoadingMore,
  };
}
