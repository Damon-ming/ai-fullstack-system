import { createAppStore } from "../app-store";

export interface HistoryState {
  activeId: string | null;
  loading: boolean;
  skipSave: boolean;
  setActiveId: (id: string | null) => void;
  beginLoad: () => void;
  finishLoad: () => void;
  clearSkipSave: () => void;
}

export const useHistoryStore = createAppStore<HistoryState>((set) => ({
  activeId: null,
  loading: false,
  skipSave: false,
  setActiveId: (activeId) => set({ activeId }),
  beginLoad: () => set({ loading: true, skipSave: false }),
  finishLoad: () => set({ loading: false, skipSave: true }),
  clearSkipSave: () => set({ skipSave: false }),
}));
