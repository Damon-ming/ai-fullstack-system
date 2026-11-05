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
  const savedTurn = useHistoryStore((state) => state.savedTurn);
  const { getTurns, refresh } = useHistory();
  const setMessages = useChatMessageStore((state) => state.setMessages);
  const abortStream = useChatMessageStore((state) => state.abortStream);
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

  // 会话内容由服务端落库，前端不再写入，只负责刷新列表
  useEffect(() => {
    if (savedTurn > 0) void refresh();
  }, [savedTurn, refresh]);

  const loadHistory = async (id: string) => {
    // 切换会话前取消进行中的流：旧流消息按 id 隔离不会污染新会话，
    // 但全局 sending 会被旧流结束时的 setSending(false) 之外的状态锁住
    abortStream();
    // 无论有无轮次都切换视图：空会话 / 拉取失败是合法状态，
    // 静默保留旧会话内容会让用户误以为在看新会话
    const turns = await getTurns(id);
    setMessages(turnsToChatMessages(turns));
    setActiveConversationId(id);
    resetSession();
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
