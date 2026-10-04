import { useHistory } from "@ming/features-history-api";
import { useChatMessageStore, useChatUiStore } from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerHistoryHook() {
  const activeId = useHistoryStore((s) => s.activeId);
  const setActiveId = useHistoryStore((s) => s.setActiveId);
  const beginLoad = useHistoryStore((s) => s.beginLoad);
  const refreshHistory = useHistoryStore((s) => s.notifyChanged);
  const revision = useHistoryStore((s) => s.revision);
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const resetSession = useChatUiStore((s) => s.resetSession);
  const { list, groups, getMessages, remove } = useHistory(revision);

  const selectChat = (id: string) => {
    beginLoad();
    setMessages(getMessages(id));
    setActiveId(id);
    resetSession();
  };

  const deleteHistory = (id: string) => {
    remove(id);
    refreshHistory();
  };

  return { list, groups, activeId, selectChat, deleteHistory };
}
