// web-app/src/packages/store/src/biz/chat-state.ts
import { createAppStore } from "../app-store";

// Chat 页面交互状态：只负责抽屉和会话生命周期。
// 当前选中会话 id 统一放在 useHistoryStore.activeConversationId。
export interface ChatUiState {
  drawerOpen: boolean;
  sessionId: number;
  toggleDrawer: () => void;
  resetSession: () => void;
}

export const useChatUiStore = createAppStore<ChatUiState>((set) => ({
  drawerOpen: true,
  sessionId: 0,
  toggleDrawer: () => set((state) => ({ drawerOpen: !state.drawerOpen })),
  resetSession: () => set((state) => ({ sessionId: state.sessionId + 1 })),
}));

// Chat 消息交互状态：只负责输入、消息和发送过程。
export interface ChatMessage {
  /** 客户端消息 key（React key + 更新定位），与服务端轮次 id 是两个概念 */
  id: string;
  /** 消息正文（用户提问 / 助手回答） */
  content: string;
  role: "user" | "assistant";
  /**
   * 是否仍在等待服务端交付（占位态）。
   * 用显式标记而不是「content === 占位文案」判断：模型真实输出
   * 可能与占位文案相同，字符串比较会误判。
   */
  pending?: boolean;
  /** 推理过程文本（SSE reasoning 事件累加），正文回答在 content */
  reasoning?: string;
  /** 是否正在输出 reasoning（收到正文后翻为 false，reasoning 折叠） */
  isReasoning?: boolean;
  /** reasoning 区域是否折叠（正文开始时自动折叠，用户可手动展开） */
  reasoningCollapsed?: boolean;
  /** 本轮异常提示（SSE error / 传输中断 / 落库失败），与正文分离，随历史落库 */
  errorMsg?: string;
  /** 服务端轮次元信息：turnId 与历史记录一致，conversationId 用于后续轮次追加 */
  turnId?: string;
  conversationId?: string;
  /** 提问时刻（Unix 秒），与历史记录 queryAt 同一时刻 */
  queryAt?: number;
}

export interface ChatMessageState {
  input: string;
  messages: ChatMessage[];
  sending: boolean;
  /** 是否启用深度推理模式（全局开关，影响下次发送） */
  reason: boolean;
  /**
   * 当前进行中的请求控制器（流式 / 同步共用）。
   * 放在全局而不是 hook 内：切换会话 / 新建会话时，
   * 旧 hook 实例已随组件重挂载丢失，只有全局才能取消旧流。
   */
  abortController: AbortController | null;
  setInput: (input: string) => void;
  setSending: (sending: boolean) => void;
  setMessages: (
    updater: ChatMessage[] | ((messages: ChatMessage[]) => ChatMessage[]),
  ) => void;
  resetMessages: () => void;
  setReason: (reason: boolean) => void;
  setAbortController: (controller: AbortController | null) => void;
  /** 取消当前进行中的请求（流式中切换会话前调用） */
  abortStream: () => void;
}

export const useChatMessageStore = createAppStore<ChatMessageState>(
  (set, get) => ({
    input: "",
    messages: [],
    sending: false,
    reason: false,
    abortController: null,
    setInput: (input) => set({ input }),
    setSending: (sending) => set({ sending }),
    setMessages: (updater) =>
      set((state) => ({
        messages:
          typeof updater === "function" ? updater(state.messages) : updater,
      })),
    resetMessages: () => set({ input: "", messages: [], sending: false }),
    setReason: (reason) => set({ reason }),
    setAbortController: (controller) => set({ abortController: controller }),
    abortStream: () => {
      const controller = get().abortController;
      if (controller) {
        controller.abort();
        set({ abortController: null });
      }
    },
  }),
);
