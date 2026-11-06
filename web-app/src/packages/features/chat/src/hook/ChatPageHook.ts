// chat/src/hook/ChatPageHook.ts
import { useEffect } from "react";
import { createLogger } from "@ming/core-log";
import {
  useChatUiStore,
  useChatUploadStore,
  useHistoryStore,
  useSearchStore,
  useKnowledgeStore,
} from "@ming/store";
import { useHistory, useSelectConversation } from "@ming/feature-history-api";
import { useDrawerUploadHook } from "@ming/feature-chat-drawer-api";

const log = createLogger("chat/page");

export function useChatPageHook() {
  const drawerOpen = useChatUiStore((state) => state.drawerOpen);
  const chatSessionId = useChatUiStore((state) => state.sessionId);
  const toggleDrawer = useChatUiStore((state) => state.toggleDrawer);
  const savedTurn = useHistoryStore((state) => state.savedTurn);
  const { refresh } = useHistory();
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

  const loadHistory = useSelectConversation();
  return {
    drawerOpen,
    chatSessionId,
    toggleDrawer,
    searchOpen,
    closeSearch,
    loadHistory,
    upload,
    uploadMessage,
    closeUpload,
    abortUpload,
    knowledgeOpen,
    closeKnowledge,
  };
}
