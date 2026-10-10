// web-app/src/packages/features/chat/src/hook/ChatPageHook.ts
import { useEffect } from "react";
import {
  useChatUiStore,
  useChatUploadStore,
  useChatMessageStore,
  useAccountStore,
  useHistoryStore,
  useSearchStore,
  useAppStore,
} from "@ming/store";
import { useHistory } from "@ming/features-history-api";
import { searchHistory } from "@ming/features-search-api";
import { useAccount, initDeviceToken } from "@ming/features-account-api";

export function useChatPageHook() {
  const drawerOpen = useChatUiStore((state) => state.drawerOpen);
  const chatSessionId = useChatUiStore((state) => state.sessionId);
  const toggleDrawer = useChatUiStore((state) => state.toggleDrawer);
  const resetSession = useChatUiStore((state) => state.resetSession);
  const setActiveHistoryId = useHistoryStore((state) => state.setActiveId);
  const historyRevision = useHistoryStore((state) => state.revision);
  const historyLoading = useHistoryStore((state) => state.loading);
  const skipHistorySave = useHistoryStore((state) => state.skipSave);
  const finishHistoryLoad = useHistoryStore((state) => state.finishLoad);
  const clearSkipHistorySave = useHistoryStore((state) => state.clearSkipSave);
  const beginHistoryLoad = useHistoryStore((state) => state.beginLoad);
  const notifyHistory = useHistoryStore((state) => state.notifyChanged);
  const {
    list: historyList,
    getMessages,
    saveMessages,
  } = useHistory(historyRevision);
  const { profile: initialAccount, update: updateAccount } = useAccount();
  const messages = useChatMessageStore((state) => state.messages);
  const setMessages = useChatMessageStore((state) => state.setMessages);
  const accountOpen = useAccountStore((state) => state.dialogOpen);
  const draftName = useAccountStore((state) => state.draftName);
  const setDraftName = useAccountStore((state) => state.setDraftName);
  const closeAccount = useAccountStore((state) => state.closeDialog);
  const setAccountProfile = useAccountStore((state) => state.setProfile);
  const searchOpen = useSearchStore((state) => state.open);
  const searchKeyword = useSearchStore((state) => state.keyword);
  const closeSearch = useSearchStore((state) => state.closeSearch);
  const setSearchKeyword = useSearchStore((state) => state.setKeyword);
  const searchResults = searchHistory(searchKeyword);
  const upload = useChatUploadStore((state) => state.upload);
  const closeUpload = useChatUploadStore((state) => state.closeUpload);

  // 进入页面时获取设备 Token，存入全局 store，后续拦截器自动携带
  useEffect(() => {
    const token = useAppStore.getState().token.deviceToken;
    if (token) return;
    initDeviceToken()
      .then((t) => useAppStore.getState().token.setDeviceToken(t))
      .catch((err) =>
        console.error("[ChatPageHook] 获取设备 Token 失败:", err),
      );
  }, []);

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
      const savedHistory = saveMessages(
        firstUserMessage.text.slice(0, 40),
        messages,
      );
      const currentHistory =
        savedHistory ??
        historyList.find(
          (item) => item.title === firstUserMessage.text.slice(0, 40),
        );
      if (currentHistory) setActiveHistoryId(currentHistory.id);
      notifyHistory();
    }
  }, [
    messages,
    historyLoading,
    skipHistorySave,
    finishHistoryLoad,
    clearSkipHistorySave,
  ]);

  useEffect(() => {
    setAccountProfile(initialAccount);
  }, [initialAccount, setAccountProfile]);

  const loadHistory = (id: string) => {
    const saved = getMessages(id);
    if (saved.length) {
      beginHistoryLoad();
      setMessages(saved);
      setActiveHistoryId(id);
      resetSession();
    }
  };
  const saveAccount = () => {
    setAccountProfile(updateAccount(draftName));
    closeAccount();
  };
  return {
    drawerOpen,
    chatSessionId,
    toggleDrawer,
    searchOpen,
    searchKeyword,
    closeSearch,
    setSearchKeyword,
    searchResults,
    accountOpen,
    draftName,
    closeAccount,
    setDraftName,
    saveAccount,
    loadHistory,
    upload,
    closeUpload,
  };
}
