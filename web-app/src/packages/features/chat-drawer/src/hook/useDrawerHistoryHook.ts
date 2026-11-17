// web-app/src/packages/features/chat-drawer/src/hook/useDrawerHistoryHook.ts
import { useState } from "react";
import { useHistory, useSelectConversation } from "@ming/feature-history-api";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerHistoryHook() {
  const activeConversationId = useHistoryStore((s) => s.activeConversationId);
  const setActiveConversationId = useHistoryStore(
    (s) => s.setActiveConversationId,
  );
  const [deleteConfirmationId, setDeleteConfirmationId] = useState<
    string | null
  >(null);
  const {
    list,
    groups,
    remove,
    pin,
    unpin,
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

  const requestDeleteHistory = (id: string) => {
    setDeleteConfirmationId(id);
  };

  const cancelDeleteHistory = () => {
    setDeleteConfirmationId(null);
  };

  const confirmDeleteHistory = () => {
    if (!deleteConfirmationId) return;
    deleteHistory(deleteConfirmationId);
    setDeleteConfirmationId(null);
  };

  return {
    list,
    groups,
    activeConversationId,
    loading,
    selectChat,
    deleteHistory,
    deleteConfirmationId,
    requestDeleteHistory,
    cancelDeleteHistory,
    confirmDeleteHistory,
    pin,
    unpin,
    hasMore,
    loadMore,
    isLoadingMore,
  };
}
