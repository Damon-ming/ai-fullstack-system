// web-app/src/packages/features/chat-drawer/src/hook/useDrawerHistoryHook.ts
import { useHistory, turnsToChatMessages } from "@ming/feature-history-api";
import {
  useChatMessageStore,
  useChatUiStore,
} from "@ming/store/biz/chat-state";
import { useHistoryStore } from "@ming/store/biz/history-state";

export function useDrawerHistoryHook() {
  const activeId = useHistoryStore((s) => s.activeId);
  const setActiveId = useHistoryStore((s) => s.setActiveId);
  const beginLoad = useHistoryStore((s) => s.beginLoad);
  const loading = useHistoryStore((s) => s.loading);
  const setMessages = useChatMessageStore((s) => s.setMessages);
  const resetSession = useChatUiStore((s) => s.resetSession);
  const { list, groups, getTurns, remove } = useHistory();

  const selectChat = async (id: string) => {
    const turns = await getTurns(id);
    const saved = turnsToChatMessages(turns);
    if (saved.length) {
      beginLoad();
      setMessages(saved);
      setActiveId(id);
      resetSession();
    }
  };

  const deleteHistory = (id: string) => {
    remove(id);
    // 删除的是当前会话时必须清空 activeId，否则下一轮发送会按该 id 重新建会话
    if (activeId === id) setActiveId(null);
  };

  return { list, groups, activeId, loading, selectChat, deleteHistory };
}
