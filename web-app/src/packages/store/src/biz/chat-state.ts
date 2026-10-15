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
  /** 推理过程文本（SSE reasoning 事件累加），正文回答在 text */
  reasoning?: string;
  /** 是否正在输出 reasoning（收到正文后翻为 false，reasoning 折叠） */
  isReasoning?: boolean;
  /** reasoning 区域是否折叠（正文开始时自动折叠，用户可手动展开） */
  reasoningCollapsed?: boolean;
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
  /** 是否启用深度推理模式（全局开关，影响下次发送） */
  reason: boolean;
  setInput: (input: string) => void;
  setSending: (sending: boolean) => void;
  setMessages: (
    updater: ChatMessage[] | ((messages: ChatMessage[]) => ChatMessage[]),
  ) => void;
  resetMessages: () => void;
  setReason: (reason: boolean) => void;
}

export const useChatMessageStore = createAppStore<ChatMessageState>((set) => ({
  input: "",
  messages: [],
  sending: false,
  reason: false,
  setInput: (input) => set({ input }),
  setSending: (sending) => set({ sending }),
  setMessages: (updater) =>
    set((state) => ({
      messages:
        typeof updater === "function" ? updater(state.messages) : updater,
    })),
  resetMessages: () => set({ input: "", messages: [], sending: false }),
  setReason: (reason) => set({ reason }),
}));
