// web-app/src/packages/store/src/biz/chat-state.ts
import { createAppStore } from "../app-store";

// Chat 页面交互状态：只负责抽屉和会话生命周期。
export interface ChatUiState {
  drawerOpen: boolean;
  sessionId: number;
  activeHistoryId: string | null;
  toggleDrawer: () => void;
  resetSession: () => void;
  setActiveHistoryId: (id: string) => void;
}

export const useChatUiStore = createAppStore<ChatUiState>((set) => ({
  drawerOpen: true,
  sessionId: 0,
  activeHistoryId: null,
  toggleDrawer: () => set((state) => ({ drawerOpen: !state.drawerOpen })),
  resetSession: () => set((state) => ({ sessionId: state.sessionId + 1 })),
  setActiveHistoryId: (activeHistoryId) => set({ activeHistoryId }),
}));

// Chat 消息交互状态：只负责输入、消息和发送过程。
export interface ChatMessage {
  id: string;
  text: string;
  role: "user" | "assistant";
  /** 思考过程文本（SSE thinking 事件累加），正文回答在 text */
  thinking?: string;
  /** SSE start 事件携带的元信息，由 hook 在流式开始时写入 */
  msgId?: string;
  conversationId?: string;
  model?: string;
  createdAt?: number;
  traceId?: string;
}

export interface ChatMessageState {
  input: string;
  messages: ChatMessage[];
  sending: boolean;
  setInput: (input: string) => void;
  setSending: (sending: boolean) => void;
  setMessages: (
    updater: ChatMessage[] | ((messages: ChatMessage[]) => ChatMessage[]),
  ) => void;
  resetMessages: () => void;
}

export const useChatMessageStore = createAppStore<ChatMessageState>((set) => ({
  input: "",
  messages: [],
  sending: false,
  setInput: (input) => set({ input }),
  setSending: (sending) => set({ sending }),
  setMessages: (updater) =>
    set((state) => ({
      messages:
        typeof updater === "function" ? updater(state.messages) : updater,
    })),
  resetMessages: () => set({ input: "", messages: [], sending: false }),
}));
