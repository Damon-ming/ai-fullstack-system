import { createAppStore } from "../app-store";

export interface HistoryState {
  activeId: string | null;
  loading: boolean;
  /** 服务端落库完成的轮次计数，每次流式对话结束自增 */
  savedTurn: number;
  setActiveId: (id: string | null) => void;
  beginLoad: () => void;
  finishLoad: () => void;
  markTurnSaved: () => void;
}

export const useHistoryStore = createAppStore<HistoryState>((set) => ({
  activeId: null,
  loading: false,
  savedTurn: 0,
  setActiveId: (activeId) => set({ activeId }),
  beginLoad: () => set({ loading: true }),
  finishLoad: () => set({ loading: false }),
  markTurnSaved: () => set((state) => ({ savedTurn: state.savedTurn + 1 })),
}));
