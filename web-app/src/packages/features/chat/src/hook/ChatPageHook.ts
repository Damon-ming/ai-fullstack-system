// web-app/src/packages/features/chat/src/hook/ChatPageHook.ts
import { useEffect } from "react";
import { createLogger } from "@ming/core-log";
import {
  useChatUiStore,
  useChatUploadStore,
  useHistoryStore,
  useSearchStore,
  useCorpusStore,
} from "@ming/store";
import type {
  ChatUiState,
  HistoryState,
  SearchState,
  ChatUploadState,
  CorpusState,
} from "@ming/store";
import { useHistory, useSelectConversation } from "@ming/feature-history-api";
import { useDrawerUploadHook } from "@ming/feature-chat-drawer-api";

const log = createLogger("chat/page");

export function useChatPageHook() {
  const drawerOpen = useChatUiStore((state: ChatUiState) => state.drawerOpen);
  const chatSessionId = useChatUiStore((state: ChatUiState) => state.sessionId);
  const toggleDrawer = useChatUiStore(
    (state: ChatUiState) => state.toggleDrawer,
  );
  const savedTurn = useHistoryStore((state: HistoryState) => state.savedTurn);
  const { refresh } = useHistory();
  const searchOpen = useSearchStore((state: SearchState) => state.open);
  const closeSearch = useSearchStore((state: SearchState) => state.closeSearch);
  const upload: ChatUploadState["upload"] = useChatUploadStore(
    (state: ChatUploadState) => state.upload,
  );
  const closeUpload = useChatUploadStore(
    (state: ChatUploadState) => state.closeUpload,
  );
  const { abortUpload, message: uploadMessage } = useDrawerUploadHook();
  const corpusOpen = useCorpusStore((state: CorpusState) => state.open);
  const closeCorpus = useCorpusStore((state: CorpusState) => state.closeCorpus);

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
    corpusOpen,
    closeCorpus,
  };
}
