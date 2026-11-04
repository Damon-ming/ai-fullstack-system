// chat/src/hook/ChatPageHook.ts
import { useEffect } from "react";
import { createLogger } from "@ming/core-log";
import {
  useChatUiStore,
  useChatUploadStore,
  useChatMessageStore,
  useAccountStore,
  useHistoryStore,
  useSearchStore,
  useKnowledgeStore,
} from "@ming/store";
import { useHistory, turnsToChatMessages } from "@ming/feature-history-api";
import { useAccount } from "@ming/feature-account-api";
import { useDrawerUploadHook } from "@ming/feature-chat-drawer-api";

const log = createLogger("chat/page");

export function useChatPageHook() {
  const drawerOpen = useChatUiStore((state) => state.drawerOpen);
  const chatSessionId = useChatUiStore((state) => state.sessionId);
  const toggleDrawer = useChatUiStore((state) => state.toggleDrawer);
  const resetSession = useChatUiStore((state) => state.resetSession);
  const setActiveConversationId = useHistoryStore(
    (state) => state.setActiveConversationId,
  );
  const historyLoading = useHistoryStore((state) => state.loading);
  const savedTurn = useHistoryStore((state) => state.savedTurn);
  const finishHistoryLoad = useHistoryStore((state) => state.finishLoad);
  const beginHistoryLoad = useHistoryStore((state) => state.beginLoad);
  const { getTurns, refresh } = useHistory();
  const setMessages = useChatMessageStore((state) => state.setMessages);
  const accountOpen = useAccountStore((state) => state.dialogOpen);
  const draftName = useAccountStore((state) => state.draftName);
  const setDraftName = useAccountStore((state) => state.setDraftName);
  const closeAccount = useAccountStore((state) => state.closeDialog);
  const { update: updateAccount } = useAccount();
  const searchOpen = useSearchStore((state) => state.open);
  const closeSearch = useSearchStore((state) => state.closeSearch);
  const upload = useChatUploadStore((state) => state.upload);
  const closeUpload = useChatUploadStore((state) => state.closeUpload);
  const { abortUpload, message: uploadMessage } = useDrawerUploadHook();
  const knowledgeOpen = useKnowledgeStore((state) => state.open);
  const closeKnowledge = useKnowledgeStore((state) => state.closeKnowledge);

  // 会话内容由服务端落库，前端不再写入，只负责刷新列表与复位加载标记
  useEffect(() => {
    if (historyLoading) finishHistoryLoad();
  }, [historyLoading, finishHistoryLoad]);

  useEffect(() => {
    if (savedTurn > 0) void refresh();
  }, [savedTurn, refresh]);

  const loadHistory = async (id: string) => {
    const turns = await getTurns(id);
    const saved = turnsToChatMessages(turns);
    if (saved.length) {
      beginHistoryLoad();
      setMessages(saved);
      setActiveConversationId(id);
      resetSession();
    }
  };
  const saveAccount = () => {
    updateAccount(draftName);
    closeAccount();
  };
  return {
    drawerOpen,
    chatSessionId,
    toggleDrawer,
    searchOpen,
    closeSearch,
    accountOpen,
    draftName,
    closeAccount,
    setDraftName,
    saveAccount,
    loadHistory,
    upload,
    uploadMessage,
    closeUpload,
    abortUpload,
    knowledgeOpen,
    closeKnowledge,
  };
}
