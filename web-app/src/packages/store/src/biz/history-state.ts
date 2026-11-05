import { createAppStore } from "../app-store";

export interface HistoryState {
  /** 当前选中的会话 id（与 HistoryItem.conversationId 同一概念） */
  activeConversationId: string | null;
  /** 服务端落库完成的轮次计数，每次流式对话结束自增 */
  savedTurn: number;
  setActiveConversationId: (id: string | null) => void;
  markTurnSaved: () => void;
}

export const useHistoryStore = createAppStore<HistoryState>((set) => ({
  activeConversationId: null,
  savedTurn: 0,
  setActiveConversationId: (activeConversationId) =>
    set({ activeConversationId }),
  markTurnSaved: () => set((state) => ({ savedTurn: state.savedTurn + 1 })),
}));
