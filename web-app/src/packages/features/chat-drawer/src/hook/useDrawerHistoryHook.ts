// web-app/src/packages/features/chat-drawer/src/hook/useDrawerHistoryHook.ts
import { useHistory } from "@ming/feature-history-api";
import { useChatMessageStore, useChatUiStore } from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerHistoryHook() {
  const activeId = useHistoryStore((s) => s.activeId);
  const setActiveId = useHistoryStore((s) => s.setActiveId);
  const beginLoad = useHistoryStore((s) => s.beginLoad);
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const resetSession = useChatUiStore((s) => s.resetSession);
  const { list, groups, getMessages, remove } = useHistory();

  const selectChat = async (id: string) => {
    const saved = await getMessages(id);
    if (saved.length) {
      beginLoad();
      setMessages(saved);
      setActiveId(id);
      resetSession();
    }
  };

  const deleteHistory = (id: string) => {
    remove(id);
  };

  return { list, groups, activeId, selectChat, deleteHistory };
}
