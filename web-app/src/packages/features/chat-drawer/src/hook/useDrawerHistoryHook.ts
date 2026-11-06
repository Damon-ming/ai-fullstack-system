// web-app/src/packages/features/chat-drawer/src/hook/useDrawerHistoryHook.ts
import { useHistory, useSelectConversation } from "@ming/feature-history-api";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerHistoryHook() {
  const activeConversationId = useHistoryStore((s) => s.activeConversationId);
  const setActiveConversationId = useHistoryStore(
    (s) => s.setActiveConversationId,
  );
  const {
    list,
    groups,
    remove,
    hasMore,
    loadMore,
    isLoadingMore,
    loading,
  } = useHistory();

  const selectChat = useSelectConversation();

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
