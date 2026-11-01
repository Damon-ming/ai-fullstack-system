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
import { useHistory } from "@ming/feature-history-api";
import { useAccount } from "@ming/feature-account-api";
import { useDrawerUploadHook } from "@ming/feature-chat-drawer-api";

const log = createLogger("chat/page");

export function useChatPageHook() {
  const drawerOpen = useChatUiStore((state) => state.drawerOpen);
  const chatSessionId = useChatUiStore((state) => state.sessionId);
  const toggleDrawer = useChatUiStore((state) => state.toggleDrawer);
  const resetSession = useChatUiStore((state) => state.resetSession);
  const setActiveHistoryId = useHistoryStore((state) => state.setActiveId);
  const historyLoading = useHistoryStore((state) => state.loading);
  const skipHistorySave = useHistoryStore((state) => state.skipSave);
  const finishHistoryLoad = useHistoryStore((state) => state.finishLoad);
  const clearSkipHistorySave = useHistoryStore((state) => state.clearSkipSave);
  const beginHistoryLoad = useHistoryStore((state) => state.beginLoad);
  const { list: historyList, getMessages, saveMessages } = useHistory();
  const messages = useChatMessageStore((state) => state.messages);
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

  useEffect(() => {
    if (historyLoading) {
      finishHistoryLoad();
      return;
    }
    if (skipHistorySave) {
      clearSkipHistorySave();
      return;
    }
    const firstUserMessage = messages.find(
      (message) => message.role === "user",
    );
    if (firstUserMessage) {
      saveMessages(firstUserMessage.text.slice(0, 40), messages);
      const currentHistory = historyList.find(
        (item) => item.title === firstUserMessage.text.slice(0, 40),
      );
      if (currentHistory) setActiveHistoryId(currentHistory.id);
    }
  }, [
    messages,
    historyLoading,
    skipHistorySave,
    finishHistoryLoad,
    clearSkipHistorySave,
  ]);

  const loadHistory = async (id: string) => {
    const saved = await getMessages(id);
    if (saved.length) {
      beginHistoryLoad();
      setMessages(saved);
      setActiveHistoryId(id);
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
